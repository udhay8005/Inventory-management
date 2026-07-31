"""Wave 2 #15 — Advanced Traceability (wms.lot.traceability SQL view).

One row per stock.lot that surfaces the end-to-end traceability chain for a
batch in a single record, so a buyer or auditor can answer "where did this lot
come from, where is it now, who consumed it, and how did it end?" without
hopping across the lot form, the supplier ledger, the movement timeline, and
the recall/quarantine notices.

Chain endpoints rolled up per lot:

  * Origin — supplier (stock.lot.wms_supplier_id), supplier batch / invoice,
    and received_on: the lot's create_date, or the FIRST inbound done move
    date when an external receipt happened later (whichever is earlier — the
    earliest evidence the batch was on the premises).
  * Current — live on-hand in issuable internal storage and a representative
    current location (the slot holding the most of this lot right now), using
    the same damage/repair-sink exclusion as the expiry-risk and supplier
    ledger views.
  * Consumption — the FIRST issue date (earliest done Scan Issue move line)
    and the animal that first issue was for (stock.picking.wms_animal_id).
  * Lifecycle endpoints — returned flag (any done move line on a picking
    flagged wms_returned), repair count (distinct done move lines that landed
    in a repair-flagged location), and destroyed flag
    (stock.lot.wms_lot_state = 'destroyed').

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no
storage), mirroring the project's other reporting views (wms.lot.expiry.risk,
wms.supplier.scorecard / ledger, wms.occupancy): drop_view_if_exists +
CREATE OR REPLACE VIEW in init(), a _table_query property, and a
staticmethod _query(). The lot id is the unique view id.
"""

from odoo import fields, models, tools


class WmsLotTraceability(models.Model):
    _name = "wms.lot.traceability"
    _description = "Lot traceability chain (supplier -> shelf -> issue -> end)"
    _auto = False
    # Order only by real view columns (no non-stored computed field): newest
    # received batches first, then the lot id for a stable tie-break.
    _order = "received_on desc, lot_id desc"
    _rec_name = "lot_id"

    lot_id = fields.Many2one("stock.lot", string="Batch / lot", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    # ---- Origin ---------------------------------------------------------
    partner_id = fields.Many2one("res.partner", string="Supplier", readonly=True)
    supplier_batch = fields.Char(readonly=True, help="Supplier's own batch / lot code.")
    supplier_invoice = fields.Char(readonly=True, help="Inbound invoice / delivery reference.")
    received_on = fields.Datetime(
        readonly=True,
        help="When this batch first appeared on the premises — the earlier of the "
        "lot record's creation and its first completed inbound move.",
    )
    expiration_date = fields.Datetime(readonly=True)

    # ---- Current --------------------------------------------------------
    on_hand = fields.Float(
        readonly=True, help="Units of this lot still in live, issuable internal storage."
    )
    current_location_id = fields.Many2one(
        "stock.location",
        string="Current location",
        readonly=True,
        help="A representative current slot — the internal location holding the "
        "most of this lot right now. Blank when nothing is on hand.",
    )

    # ---- Consumption ----------------------------------------------------
    first_issue_date = fields.Datetime(
        readonly=True, help="Earliest completed Scan Issue of this lot, if any."
    )
    animal_id = fields.Many2one(
        "wms.animal",
        string="Animal / cow",
        readonly=True,
        help="The animal the first issue of this lot was recorded against, when set.",
    )

    # ---- Lifecycle endpoints -------------------------------------------
    returned = fields.Boolean(
        readonly=True,
        help="True when any completed movement of this lot belongs to a transfer "
        "flagged as a returnable item that came back (wms_returned).",
    )
    repair_count = fields.Integer(
        readonly=True,
        help="Number of completed movements of this lot into a repair-station "
        "location — how many times this batch went through repair.",
    )
    destroyed = fields.Boolean(
        readonly=True, help="True when the lot's lifecycle state is 'destroyed'."
    )
    lot_state = fields.Selection(
        [
            ("available", "Available"),
            ("quarantine", "Quarantine"),
            ("recalled", "Recalled"),
            ("destroyed", "Destroyed"),
        ],
        readonly=True,
        help="Current lifecycle state of the lot.",
    )

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # Each CTE answers one chain question, keyed on lot id, then LEFT JOINed
        # onto every stock_lot so even a freshly received batch with no movement
        # yet appears (its current/consumption/lifecycle columns simply blank).
        #
        # NOTE: no literal percent sign anywhere in this string — _table_query
        # inlines the SQL into parameterized searches and psycopg2 would choke
        # on a stray percent. Write "percent" in prose if ever needed.
        return """
            WITH oh AS (
                -- Live, issuable on-hand per lot (excludes damage/repair sinks),
                -- matching the expiry-risk and supplier-ledger views.
                SELECT sq.lot_id,
                       SUM(sq.quantity) AS on_hand,
                       MAX(sq.company_id) AS company_id
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sl.wms_location_type IN ('slot', 'floor')
                   AND sq.lot_id IS NOT NULL
                   AND sq.quantity > 0
                 GROUP BY sq.lot_id
            ),
            cur_loc AS (
                -- Representative current location: the issuable internal slot
                -- holding the MOST of this lot right now (one row per lot).
                SELECT DISTINCT ON (sq.lot_id)
                       sq.lot_id,
                       sq.location_id AS current_location_id
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sl.wms_location_type IN ('slot', 'floor')
                   AND sq.lot_id IS NOT NULL
                   AND sq.quantity > 0
                 ORDER BY sq.lot_id, sq.quantity DESC, sq.location_id
            ),
            inbound AS (
                -- First completed inbound move (external source -> internal) per
                -- lot: the earliest physical receipt evidence.
                SELECT sml.lot_id,
                       MIN(sml.date) AS first_inbound_date
                  FROM stock_move_line sml
                  JOIN stock_location src ON src.id = sml.location_id
                  JOIN stock_location dst ON dst.id = sml.location_dest_id
                 WHERE sml.state = 'done'
                   AND sml.lot_id IS NOT NULL
                   AND src.usage != 'internal'
                   AND dst.usage = 'internal'
                 GROUP BY sml.lot_id
            ),
            first_issue AS (
                -- Earliest completed Scan Issue per lot + the animal it was for.
                SELECT DISTINCT ON (sml.lot_id)
                       sml.lot_id,
                       sml.date AS first_issue_date,
                       sp.wms_animal_id AS animal_id
                  FROM stock_move_line sml
                  JOIN stock_picking sp ON sp.id = sml.picking_id
                 WHERE sml.state = 'done'
                   AND sml.lot_id IS NOT NULL
                   AND sp.wms_is_scan_issue = TRUE
                 ORDER BY sml.lot_id, sml.date, sml.id
            ),
            returns AS (
                -- Lot touched by any transfer that was flagged returned.
                SELECT DISTINCT sml.lot_id
                  FROM stock_move_line sml
                  JOIN stock_picking sp ON sp.id = sml.picking_id
                 WHERE sml.state = 'done'
                   AND sml.lot_id IS NOT NULL
                   AND COALESCE(sp.wms_returned, FALSE) = TRUE
            ),
            repairs AS (
                -- Completed movements of this lot INTO a repair-station location.
                SELECT sml.lot_id,
                       COUNT(*) AS repair_count
                  FROM stock_move_line sml
                  JOIN stock_location dst ON dst.id = sml.location_dest_id
                 WHERE sml.state = 'done'
                   AND sml.lot_id IS NOT NULL
                   AND COALESCE(dst.wms_is_repair, FALSE) = TRUE
                 GROUP BY sml.lot_id
            )
            SELECT lot.id AS id,
                   lot.id AS lot_id,
                   lot.product_id AS product_id,
                   COALESCE(oh.company_id, lot.company_id) AS company_id,
                   lot.wms_supplier_id AS partner_id,
                   lot.wms_supplier_batch AS supplier_batch,
                   lot.wms_supplier_invoice AS supplier_invoice,
                   LEAST(
                       lot.create_date,
                       COALESCE(inbound.first_inbound_date, lot.create_date)
                   ) AS received_on,
                   lot.expiration_date AS expiration_date,
                   COALESCE(oh.on_hand, 0.0) AS on_hand,
                   cur_loc.current_location_id AS current_location_id,
                   first_issue.first_issue_date AS first_issue_date,
                   first_issue.animal_id AS animal_id,
                   COALESCE(ret.lot_id IS NOT NULL, FALSE) AS returned,
                   COALESCE(repairs.repair_count, 0) AS repair_count,
                   (lot.wms_lot_state = 'destroyed') AS destroyed,
                   lot.wms_lot_state AS lot_state
              FROM stock_lot lot
              LEFT JOIN oh ON oh.lot_id = lot.id
              LEFT JOIN cur_loc ON cur_loc.lot_id = lot.id
              LEFT JOIN inbound ON inbound.lot_id = lot.id
              LEFT JOIN first_issue ON first_issue.lot_id = lot.id
              LEFT JOIN returns ret ON ret.lot_id = lot.id
              LEFT JOIN repairs ON repairs.lot_id = lot.id
        """

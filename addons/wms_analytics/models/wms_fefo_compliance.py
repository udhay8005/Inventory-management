"""Wave 2 #7 (piece 2) — FEFO compliance of Scan Issues.

The Scan Issue wizard plans deductions oldest-arrival-first (FIFO). For
perishable stock the trust really wants *FEFO* — first-expiry-first-out — so a
short-dated batch is never left on the shelf while a longer-dated one is issued.
This read-only report measures, per issued move line of a lot-tracked product,
whether the lot actually drawn was the earliest-expiry batch available.

Implemented as an ``_auto=False`` SQL view (read-only, always fresh, no
storage), mirroring wms.lot.expiry.risk and the project's other reporting views.

Scope: every DONE ``stock.move.line`` that
  * belongs to a Scan Issue picking (``stock_picking.wms_is_scan_issue``),
  * carries a lot whose product is lot-tracked and has an expiration date, and
  * left internal storage (an outbound consumption, not an internal shuffle).

Compliance (best-effort): the drawn lot is FEFO-compliant when its expiry is
the *earliest* among the product's lots that currently have live internal stock
(plus the drawn lot itself, which may now be empty). This is a current-state
proxy — Odoo keeps no per-instant snapshot of which batches were on the shelf at
issue time — so a long-since-consumed shorter-dated batch can't retroactively
fail an old issue, but the rate is a sound ongoing signal. A month bucket is
exposed so a compliance-rate graph works (average of the boolean per month).
"""

from odoo import fields, models, tools


class WmsFefoCompliance(models.Model):
    _name = "wms.fefo.compliance"
    _description = "FEFO compliance of Scan Issues (earliest-expiry-first)"
    _auto = False
    _order = "issue_date desc, id desc"
    _rec_name = "lot_id"

    move_line_id = fields.Many2one("stock.move.line", readonly=True)
    picking_id = fields.Many2one("stock.picking", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    lot_id = fields.Many2one("stock.lot", readonly=True, string="Lot issued")
    company_id = fields.Many2one("res.company", readonly=True)
    quantity = fields.Float(readonly=True, help="Quantity issued on this move line.")
    issue_date = fields.Datetime(readonly=True, help="When the issue move line completed.")
    month = fields.Date(readonly=True, help="Issue month (first day) for trend grouping.")
    drawn_expiry = fields.Datetime(
        readonly=True, help="Expiration date of the lot that was actually issued."
    )
    earliest_expiry = fields.Datetime(
        readonly=True,
        help="Earliest expiration date among the product's lots that currently "
        "have live internal stock (the FEFO target).",
    )
    compliant = fields.Boolean(
        readonly=True,
        help="True when the issued lot's expiry is the earliest available — i.e. "
        "the issue honoured first-expiry-first-out.",
    )

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @staticmethod
    def _query():
        # earliest: the minimum live-stock expiry per product, computed from
        # lots that currently have positive on-hand in internal storage
        # (excluding the damage/repair sinks, exactly like the expiry-risk and
        # disposal views). Compared to the drawn lot's own expiry with a small
        # tolerance: an issue is compliant when no longer-on-shelf batch was
        # strictly shorter-dated than the one drawn. COALESCE keeps a product
        # whose other batches are all gone (earliest = drawn) compliant.
        return """
            WITH live_expiry AS (
                SELECT lot.product_id AS product_id,
                       MIN(lot.expiration_date) AS earliest_expiry
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                  JOIN stock_lot lot ON lot.id = sq.lot_id
                 WHERE sl.usage = 'internal'
                   AND COALESCE(sl.wms_is_damage, FALSE) = FALSE
                   AND COALESCE(sl.wms_is_repair, FALSE) = FALSE
                   AND sq.quantity > 0
                   AND lot.expiration_date IS NOT NULL
                 GROUP BY lot.product_id
            )
            SELECT ml.id AS id,
                   ml.id AS move_line_id,
                   mv.picking_id AS picking_id,
                   ml.product_id AS product_id,
                   ml.lot_id AS lot_id,
                   ml.company_id AS company_id,
                   ml.quantity AS quantity,
                   ml.date AS issue_date,
                   date_trunc('month', ml.date)::date AS month,
                   lot.expiration_date AS drawn_expiry,
                   LEAST(lot.expiration_date,
                         COALESCE(le.earliest_expiry, lot.expiration_date))
                       AS earliest_expiry,
                   (lot.expiration_date
                        <= COALESCE(le.earliest_expiry, lot.expiration_date)
                        + INTERVAL '1 second') AS compliant
              FROM stock_move_line ml
              JOIN stock_move mv ON mv.id = ml.move_id
              JOIN stock_picking p ON p.id = mv.picking_id
              JOIN stock_lot lot ON lot.id = ml.lot_id
              JOIN stock_location src ON src.id = ml.location_id
              LEFT JOIN live_expiry le ON le.product_id = ml.product_id
             WHERE ml.state = 'done'
               AND COALESCE(p.wms_is_scan_issue, FALSE) = TRUE
               AND ml.lot_id IS NOT NULL
               AND lot.expiration_date IS NOT NULL
               AND src.usage = 'internal'
        """

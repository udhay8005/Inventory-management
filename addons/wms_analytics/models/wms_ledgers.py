"""Wave 2 — Lot / Product / Warehouse movement ledgers.

Three chronological movement views over *done* ``stock.move.line`` rows (the
authoritative record of physical stock that actually moved). Each row is one
move line — a dated transfer of a quantity of a product (and, where tracked, a
lot) from a source location to a destination location. A ``direction`` is
derived from the usage of the two endpoints:

  * ``in``       — arriving from outside (supplier / inventory / production /
                   customer return): source NOT internal, destination internal;
  * ``out``      — leaving the warehouse (issue / scrap / delivery): source
                   internal, destination NOT internal;
  * ``internal`` — both endpoints internal (a put-away, relocation, undo, or a
                   damage/repair sink move).

Three models share the same projection but key on different dimensions so each
gets a natural group-by default and rec_name:

  * ``wms.lot.ledger``        — lot-centric (rows restricted to lot-tracked moves);
  * ``wms.product.ledger``    — product-centric (all done move lines);
  * ``wms.warehouse.ledger``  — location/warehouse-centric (destination warehouse).

All three are ``_auto=False`` read-only SQL views, mirroring the project's
other reporting views (wms.lot.expiry.risk, wms.stock.health, ...). Unique row
ids come from ``row_number() OVER ()`` because a single move line maps to one
ledger row per model.
"""

from odoo import fields, models, tools

# Shared SELECT body for the three ledgers. ``%(extra_where)s`` lets the
# lot ledger add its "lot_id IS NOT NULL" restriction without duplicating the
# whole projection. Direction is computed from endpoint usage. We only count
# done move lines with a positive moved quantity.
_LEDGER_SELECT = """
    SELECT row_number() OVER (ORDER BY sml.date, sml.id) AS id,
           sml.id              AS move_line_id,
           sml.date            AS date,
           sml.product_id      AS product_id,
           sml.lot_id          AS lot_id,
           sml.location_id     AS location_id,
           sml.location_dest_id AS location_dest_id,
           sml.quantity        AS quantity,
           sml.picking_id      AS picking_id,
           sml.company_id      AS company_id,
           src.warehouse_id    AS src_warehouse_id,
           dest.warehouse_id   AS dest_warehouse_id,
           CASE
               WHEN src.usage = 'internal' AND dest.usage = 'internal'
                    THEN 'internal'
               WHEN src.usage != 'internal' AND dest.usage = 'internal'
                    THEN 'in'
               WHEN src.usage = 'internal' AND dest.usage != 'internal'
                    THEN 'out'
               ELSE 'internal'
           END AS direction
      FROM stock_move_line sml
      JOIN stock_location src  ON src.id  = sml.location_id
      JOIN stock_location dest ON dest.id = sml.location_dest_id
     WHERE sml.state = 'done'
       AND sml.quantity > 0
       %(extra_where)s
"""

_DIRECTION_SELECTION = [
    ("in", "In (receipt / return)"),
    ("out", "Out (issue / delivery)"),
    ("internal", "Internal (move / put-away)"),
]


class WmsLedgerMixin(models.AbstractModel):
    """Common columns and SQL plumbing for the three movement ledgers."""

    _name = "wms.ledger.mixin"
    _description = "WMS movement ledger (abstract base)"
    _auto = False
    _order = "date desc, id desc"

    move_line_id = fields.Many2one("stock.move.line", readonly=True, string="Move line")
    date = fields.Datetime(readonly=True, help="When the stock physically moved.")
    product_id = fields.Many2one("product.product", readonly=True)
    lot_id = fields.Many2one("stock.lot", readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True, string="From")
    location_dest_id = fields.Many2one("stock.location", readonly=True, string="To")
    quantity = fields.Float(readonly=True, help="Quantity moved on this line.")
    picking_id = fields.Many2one("stock.picking", readonly=True, string="Transfer")
    company_id = fields.Many2one("res.company", readonly=True)
    src_warehouse_id = fields.Many2one("stock.warehouse", readonly=True, string="From warehouse")
    dest_warehouse_id = fields.Many2one("stock.warehouse", readonly=True, string="To warehouse")
    direction = fields.Selection(
        _DIRECTION_SELECTION,
        readonly=True,
        help="Whether this move brought stock in, sent it out, or relocated it "
        "internally — derived from the usage of the source and destination "
        "locations.",
    )

    # ``extra_where`` is an SQL fragment (already including a leading AND) that a
    # concrete ledger may use to narrow the row set. Default: no restriction.
    _ledger_extra_where = ""

    @property
    def _table_query(self):
        return self._query()

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("CREATE OR REPLACE VIEW %s AS (%s)" % (self._table, self._query()))

    @classmethod
    def _query(cls):
        return _LEDGER_SELECT % {"extra_where": cls._ledger_extra_where}


class WmsLotLedger(models.Model):
    """Lot-centric movement ledger: every done move of a lot-tracked line."""

    _name = "wms.lot.ledger"
    _description = "Lot movement ledger"
    _inherit = "wms.ledger.mixin"
    _auto = False
    _order = "date desc, id desc"
    _rec_name = "lot_id"

    # Only lot-tracked moves belong in a lot ledger.
    _ledger_extra_where = "AND sml.lot_id IS NOT NULL"


class WmsProductLedger(models.Model):
    """Product-centric movement ledger: every done move line."""

    _name = "wms.product.ledger"
    _description = "Product movement ledger"
    _inherit = "wms.ledger.mixin"
    _auto = False
    _order = "date desc, id desc"
    _rec_name = "product_id"


class WmsWarehouseLedger(models.Model):
    """Warehouse/location-centric movement ledger: every done move line.

    Same projection as the product ledger but defaults its grouping to the
    destination location / warehouse so a keeper can read 'what landed where'.
    """

    _name = "wms.warehouse.ledger"
    _description = "Warehouse movement ledger"
    _inherit = "wms.ledger.mixin"
    _auto = False
    _order = "date desc, id desc"
    _rec_name = "location_dest_id"

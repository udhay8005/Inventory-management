from odoo import api, fields, models, tools


class WmsProductStockReport(models.Model):
    """One row per (product, slot) for every quant currently on hand.

    Answers the operator's #1 question instantly: "I have product X — show
    me every slot it lives in, oldest stock first." Group-by product in
    the UI for a per-product breakdown across the warehouse.
    """
    _name = "wms.product.stock.report"
    _description = "Stock by product — every slot, FIFO ordered"
    _auto = False
    _order = "product_id, in_date asc"

    product_id = fields.Many2one("product.product", readonly=True)
    product_barcode = fields.Char(readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True, string="Slot")
    divider_id = fields.Many2one("stock.location", readonly=True)
    level_id = fields.Many2one("stock.location", readonly=True)
    rack_id = fields.Many2one("stock.location", readonly=True)
    quantity = fields.Float(readonly=True)
    reserved_quantity = fields.Float(readonly=True)
    available_quantity = fields.Float(readonly=True)
    in_date = fields.Datetime(readonly=True)
    age_days = fields.Integer(readonly=True)
    is_oldest = fields.Boolean(
        readonly=True,
        help="Marks the next slot FIFO picking will draw from.",
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW wms_product_stock_report AS
              WITH ranked AS (
                  SELECT q.id,
                         q.product_id,
                         q.location_id,
                         d.id AS divider_id,
                         l.id AS level_id,
                         r.id AS rack_id,
                         q.quantity,
                         q.reserved_quantity,
                         q.quantity - q.reserved_quantity AS available_quantity,
                         q.in_date,
                         EXTRACT(DAY FROM (now() - COALESCE(q.in_date, q.create_date)))::int AS age_days,
                         ROW_NUMBER() OVER (
                             PARTITION BY q.product_id
                             ORDER BY q.in_date ASC, q.id ASC
                         ) AS rn
                    FROM stock_quant q
                    JOIN stock_location s ON s.id = q.location_id
                                         AND s.wms_location_type = 'slot'
                    JOIN stock_location d ON d.id = s.location_id
                    JOIN stock_location l ON l.id = d.location_id
                    JOIN stock_location r ON r.id = l.location_id
                   WHERE q.quantity > 0
              )
              SELECT ranked.id,
                     ranked.product_id,
                     pp.barcode AS product_barcode,
                     ranked.location_id,
                     ranked.divider_id,
                     ranked.level_id,
                     ranked.rack_id,
                     ranked.quantity,
                     ranked.reserved_quantity,
                     ranked.available_quantity,
                     ranked.in_date,
                     ranked.age_days,
                     (ranked.rn = 1) AS is_oldest
                FROM ranked
                JOIN product_product pp ON pp.id = ranked.product_id
        """)

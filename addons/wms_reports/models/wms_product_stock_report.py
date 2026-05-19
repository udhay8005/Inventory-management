from odoo import api, fields, models, tools


class WmsProductStockReport(models.Model):
    """One row per (product, stocking-location) for every quant on hand.

    Includes both rack slots AND floor zones (non-rack open storage).
    For floor rows the compartment/rack columns are NULL — UI shows
    them as a dash. FIFO `is_oldest` still works across the whole set.
    """

    _name = "wms.product.stock.report"
    _description = "Stock by product — every location, FIFO ordered"
    _auto = False
    _order = "product_id, in_date asc"

    product_id = fields.Many2one("product.product", readonly=True)
    product_barcode = fields.Char(readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True, string="Location")
    location_kind = fields.Selection(
        [("slot", "Rack slot"), ("floor", "Floor zone")],
        readonly=True,
        string="Kind",
    )
    compartment_id = fields.Many2one("stock.location", readonly=True)
    rack_id = fields.Many2one("stock.location", readonly=True)
    quantity = fields.Float(readonly=True)
    reserved_quantity = fields.Float(readonly=True)
    available_quantity = fields.Float(readonly=True)
    in_date = fields.Datetime(readonly=True)
    age_days = fields.Integer(readonly=True)
    is_oldest = fields.Boolean(
        readonly=True,
        help="Marks the next location FIFO picking will draw from for this product.",
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_product_stock_report AS
              WITH ranked AS (
                  SELECT q.id,
                         q.product_id,
                         q.location_id,
                         s.wms_location_type AS location_kind,
                         c.id AS compartment_id,
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
                    JOIN stock_location s
                      ON s.id = q.location_id
                     AND s.wms_location_type IN ('slot', 'floor')
                    -- LEFT joins so floor rows survive (no rack chain).
                    LEFT JOIN stock_location c
                      ON c.id = s.location_id
                     AND c.wms_location_type = 'compartment'
                    LEFT JOIN stock_location r
                      ON r.id = c.location_id
                     AND r.wms_location_type = 'rack'
                   WHERE q.quantity > 0
              )
              SELECT ranked.id,
                     ranked.product_id,
                     pp.barcode AS product_barcode,
                     ranked.location_id,
                     ranked.location_kind,
                     ranked.compartment_id,
                     ranked.rack_id,
                     ranked.quantity,
                     ranked.reserved_quantity,
                     ranked.available_quantity,
                     ranked.in_date,
                     ranked.age_days,
                     (ranked.rn = 1) AS is_oldest
                FROM ranked
                JOIN product_product pp ON pp.id = ranked.product_id
        """
        )

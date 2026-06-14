from odoo import api, fields, models, tools


class WmsOldestStockReport(models.Model):
    """Read-only SQL view: every live quant ordered by in_date (FIFO age).
    Joins up the parent chain so dashboards can group by rack/compartment
    without writing complex domains.
    """

    _name = "wms.oldest.stock.report"
    _description = "Oldest stock first (FIFO view)"
    _auto = False
    _order = "in_date asc"

    product_id = fields.Many2one("product.product", readonly=True)
    location_id = fields.Many2one("stock.location", readonly=True, string="Slot")
    compartment_id = fields.Many2one("stock.location", readonly=True)
    rack_id = fields.Many2one("stock.location", readonly=True)
    quantity = fields.Float(readonly=True)
    in_date = fields.Datetime(readonly=True)
    age_days = fields.Integer(readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_oldest_stock_report AS
              SELECT q.id AS id,
                     q.product_id,
                     q.location_id,
                     c.id AS compartment_id,
                     r.id AS rack_id,
                     q.quantity,
                     q.in_date,
                     EXTRACT(DAY FROM (now() - COALESCE(q.in_date, q.create_date)))::int AS age_days
                FROM stock_quant q
                JOIN stock_location s ON s.id = q.location_id
                                     AND s.wms_location_type IN ('slot', 'floor')
                -- LEFT so floor-zone stock (which has no compartment/rack
                -- chain) still shows in the FIFO-age report. The old INNER
                -- joins silently dropped every floor quant, contradicting the
                -- planner / scan / sibling reports that treat slot+floor alike.
                LEFT JOIN stock_location c ON c.id = s.location_id
                                          AND c.wms_location_type = 'compartment'
                LEFT JOIN stock_location r ON r.id = c.location_id
                                          AND r.wms_location_type = 'rack'
               WHERE q.quantity > 0
        """
        )

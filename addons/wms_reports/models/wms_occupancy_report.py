from odoo import api, fields, models, tools


class WmsOccupancyReport(models.Model):
    """One row per slot: capacity, qty on hand, % occupied, distinct products."""
    _name = "wms.occupancy.report"
    _description = "Slot occupancy"
    _auto = False
    _order = "occupancy_pct desc"

    location_id = fields.Many2one("stock.location", readonly=True, string="Slot")
    rack_id = fields.Many2one("stock.location", readonly=True)
    capacity = fields.Float(readonly=True)
    on_hand = fields.Float(readonly=True)
    occupancy_pct = fields.Float(readonly=True)
    distinct_products = fields.Integer(readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW wms_occupancy_report AS
              SELECT s.id AS id,
                     s.id AS location_id,
                     r.id AS rack_id,
                     s.wms_capacity_units AS capacity,
                     COALESCE(SUM(q.quantity), 0) AS on_hand,
                     CASE WHEN s.wms_capacity_units > 0
                          THEN COALESCE(SUM(q.quantity), 0) / s.wms_capacity_units * 100
                          ELSE 0 END AS occupancy_pct,
                     COUNT(DISTINCT q.product_id) AS distinct_products
                FROM stock_location s
                JOIN stock_location d ON d.id = s.location_id
                JOIN stock_location r ON r.id = d.location_id
                LEFT JOIN stock_quant q ON q.location_id = s.id AND q.quantity > 0
               WHERE s.wms_location_type = 'slot'
            GROUP BY s.id, r.id
        """)

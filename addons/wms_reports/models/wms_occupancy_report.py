from odoo import api, fields, models, tools


class WmsOccupancyReport(models.Model):
    """One row per stocking location (slot OR floor zone): capacity, qty,
    occupancy %, distinct product count.

    Walks the new Rack → Compartment → Slot tree: the slot's location_id
    is its compartment, the compartment's location_id is its rack.
    """

    _name = "wms.occupancy.report"
    _description = "Location occupancy (slots + floor zones)"
    _auto = False
    _order = "occupancy_pct desc"

    location_id = fields.Many2one("stock.location", readonly=True, string="Location")
    location_kind = fields.Selection(
        [("slot", "Rack slot"), ("floor", "Floor zone")],
        readonly=True,
    )
    compartment_id = fields.Many2one("stock.location", readonly=True)
    rack_id = fields.Many2one("stock.location", readonly=True)
    capacity = fields.Float(readonly=True)
    on_hand = fields.Float(readonly=True)
    occupancy_pct = fields.Float(readonly=True)
    distinct_products = fields.Integer(readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_occupancy_report AS
              SELECT s.id AS id,
                     s.id AS location_id,
                     s.wms_location_type AS location_kind,
                     c.id AS compartment_id,
                     r.id AS rack_id,
                     s.wms_capacity_units AS capacity,
                     COALESCE(SUM(q.quantity), 0) AS on_hand,
                     CASE WHEN s.wms_capacity_units > 0
                          THEN COALESCE(SUM(q.quantity), 0) / s.wms_capacity_units * 100
                          ELSE 0 END AS occupancy_pct,
                     COUNT(DISTINCT q.product_id) AS distinct_products
                FROM stock_location s
                LEFT JOIN stock_location c
                  ON c.id = s.location_id AND c.wms_location_type = 'compartment'
                LEFT JOIN stock_location r
                  ON r.id = c.location_id AND r.wms_location_type = 'rack'
                LEFT JOIN stock_quant q
                  ON q.location_id = s.id AND q.quantity > 0
               WHERE s.wms_location_type IN ('slot', 'floor')
            GROUP BY s.id, c.id, r.id
        """
        )

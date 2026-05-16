from odoo import api, fields, models, tools


class WmsReorderSummary(models.Model):
    """Sum reorder quantities per vendor so buyers see a single shopping list."""

    _name = "wms.reorder.summary"
    _description = "Reorder summary by vendor"
    _auto = False
    _order = "total_qty desc"

    partner_id = fields.Many2one("res.partner", readonly=True, string="Vendor")
    product_count = fields.Integer(readonly=True)
    total_qty = fields.Float(readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_reorder_summary AS
              SELECT MIN(f.id) AS id,
                     ps.partner_id,
                     COUNT(DISTINCT f.product_id) AS product_count,
                     SUM(f.reorder_qty)           AS total_qty
                FROM wms_forecast f
                LEFT JOIN product_supplierinfo ps
                       ON ps.product_tmpl_id = (
                          SELECT pt.id FROM product_product pp
                            JOIN product_template pt ON pt.id = pp.product_tmpl_id
                           WHERE pp.id = f.product_id LIMIT 1
                       )
               WHERE f.reorder_qty > 0
            GROUP BY ps.partner_id
        """
        )

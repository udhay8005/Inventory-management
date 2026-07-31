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
                     pref.partner_id,
                     COUNT(DISTINCT f.product_id) AS product_count,
                     SUM(f.reorder_qty)           AS total_qty
                FROM wms_forecast f
                JOIN product_product pp ON pp.id = f.product_id
                -- ONE preferred supplier per product before aggregating.
                -- A plain template join fanned a product with two vendors
                -- into BOTH vendor totals (double-count) and missed
                -- variant-level supplierinfo. This lateral picks the single
                -- best seller for THIS variant - mirroring Odoo's own
                -- seller_ids[:1] (variant-specific match first, then lowest
                -- sequence) - so each product's reorder_qty lands in exactly
                -- one vendor bucket (or the NULL "no vendor" bucket).
                LEFT JOIN LATERAL (
                    SELECT ps.partner_id
                      FROM product_supplierinfo ps
                     WHERE ps.product_tmpl_id = pp.product_tmpl_id
                       AND (ps.product_id = pp.id OR ps.product_id IS NULL)
                     ORDER BY (ps.product_id = pp.id) DESC, ps.sequence, ps.id
                     LIMIT 1
                ) pref ON TRUE
               WHERE f.reorder_qty > 0
            GROUP BY pref.partner_id
        """
        )

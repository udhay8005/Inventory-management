from odoo import api, fields, models


class WmsForecast(models.Model):
    _name = "wms.forecast"
    _description = "Per-product forecast"
    _order = "velocity_class, reorder_qty desc"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    horizon_days = fields.Integer(default=30, required=True)
    predicted_qty = fields.Float(readonly=True)
    daily_avg = fields.Float(readonly=True)
    monthly_avg = fields.Float(readonly=True)
    reorder_qty = fields.Float(readonly=True)
    reorder_date = fields.Date(readonly=True)
    velocity_class = fields.Selection(
        [("fast", "Fast"), ("normal", "Normal"), ("slow", "Slow"), ("dead", "Dead")],
        readonly=True,
    )
    is_consumable = fields.Boolean(readonly=True)
    last_trained = fields.Datetime(readonly=True)
    model_name = fields.Char(readonly=True)
    rmse = fields.Float(readonly=True)
    on_hand = fields.Float(readonly=True)
    lead_time_days = fields.Integer(readonly=True)
    safety_stock = fields.Float(readonly=True)
    note = fields.Char(readonly=True)
    unit_cost = fields.Float(
        string="Unit cost", compute="_compute_stock_value", store=True, readonly=True
    )
    stock_value = fields.Float(
        string="Stock value",
        compute="_compute_stock_value",
        store=True,
        readonly=True,
        help="On-hand x unit cost. On the Dead Stock view this is the capital "
        "tied up in non-moving stock the trust could free by consuming it.",
    )

    @api.depends("on_hand", "product_id")
    def _compute_stock_value(self):
        for rec in self:
            cost = rec.product_id.standard_price or 0.0
            rec.unit_cost = cost
            rec.stock_value = (rec.on_hand or 0.0) * cost

    _product_unique = models.Constraint(
        "UNIQUE(product_id)",
        "One forecast row per product.",
    )

    def action_retrain(self):
        self.env["wms.forecast.engine"].train_for_products(self.product_id)

    def action_push_to_po(self):
        """Create a draft purchase.order for the suggested qty using the
        product's main supplier. Operator reviews & confirms."""
        self.ensure_one()
        if self.reorder_qty <= 0:
            return
        supplier = self.product_id.seller_ids[:1]
        if not supplier:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "title": "No vendor",
                    "message": "Configure a vendor on the product first.",
                },
            }
        # Odoo 19 renamed purchase.order.line.product_uom → product_uom_id.
        po = self.env["purchase.order"].create(
            {
                "partner_id": supplier.partner_id.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_id.id,
                            "product_qty": self.reorder_qty,
                            "name": self.product_id.display_name,
                            "date_planned": fields.Date.context_today(self),
                            "product_uom_id": self.product_id.uom_id.id,
                            "price_unit": supplier.price or 0.0,
                        },
                    )
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
        }


class WmsForecastHistory(models.Model):
    _name = "wms.forecast.history"
    _description = "Forecast training snapshot"
    _order = "trained_at desc"

    product_id = fields.Many2one("product.product", required=True, index=True)
    trained_at = fields.Datetime(default=fields.Datetime.now, index=True)
    model_name = fields.Char()
    predicted_qty = fields.Float()
    rmse = fields.Float()
    velocity_class = fields.Char()

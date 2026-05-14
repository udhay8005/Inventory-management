import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

from . import forecasting

_logger = logging.getLogger(__name__)


class WmsForecastEngine(models.AbstractModel):
    _name = "wms.forecast.engine"
    _description = "Forecast trainer (cron-callable)"

    @api.model
    def run_all_forecasts(self):
        """Entry point called by cron and the optional ai_worker.

        In Odoo 19 a "trackable" product has `is_storable=True` (the legacy
        `type='product'` was retired). We forecast every storable product
        and skip services / combos.
        """
        products = self.env["product.product"].search([
            ("active", "=", True),
            ("is_storable", "=", True),
        ])
        _logger.info("wms_ai_forecast: training %d products", len(products))
        self.train_for_products(products)

    def train_for_products(self, products):
        for product in products:
            try:
                self._train_one(product)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("forecast train failed for %s: %s",
                                product.display_name, exc)

    def _gather_outflow(self, product):
        """Return list of (datetime, qty) — daily outflow events."""
        self.env.cr.execute(
            """
            SELECT date_trunc('day', sm.date) AS d,
                   COALESCE(SUM(sm.product_uom_qty), 0)
              FROM stock_move sm
              JOIN stock_location lsrc ON lsrc.id = sm.location_id
              JOIN stock_location ldst ON ldst.id = sm.location_dest_id
             WHERE sm.product_id = %s
               AND sm.state = 'done'
               AND lsrc.usage = 'internal'
               AND ldst.usage IN ('customer', 'production')
               AND sm.date >= now() - INTERVAL '2 years'
             GROUP BY d
             ORDER BY d
            """,
            (product.id,),
        )
        return [(row[0], float(row[1])) for row in self.env.cr.fetchall()]

    def _on_hand(self, product):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id.usage", "=", "internal"),
        ])
        return sum(q.quantity for q in quants)

    def _on_order(self, product):
        # Confirmed POs not yet received
        lines = self.env["purchase.order.line"].search([
            ("product_id", "=", product.id),
            ("state", "in", ("purchase", "done")),
        ])
        return sum(l.product_qty - l.qty_received for l in lines)

    def _lead_time(self, product):
        seller = product.seller_ids[:1]
        return int(seller.delay) if seller else 7

    def _safety_stock(self, product):
        # If you use stock.warehouse.orderpoint, prefer that; else 0.
        op = self.env["stock.warehouse.orderpoint"].search([
            ("product_id", "=", product.id),
        ], limit=1)
        return op.product_min_qty if op else 0.0

    def _train_one(self, product):
        observations = self._gather_outflow(product)

        # In Odoo 19 `product.type` is consu/service/combo; the AI's old
        # consumable/reusable split keyed off type='consu'. We now key off
        # whether the product has *any* movement history — zero-history
        # products are flagged "monitor only" regardless of nominal type.
        note = ""
        if not observations:
            result = forecasting.ForecastResult(0, 0, 0, "Manual", 0, "dead")
            note = "No usage history yet — monitor only"
        else:
            result = forecasting.forecast(observations, horizon_days=30)

        on_hand = self._on_hand(product)
        on_order = self._on_order(product)
        lead = self._lead_time(product)
        safety = self._safety_stock(product)
        reorder_qty, reorder_date = forecasting.reorder_recommendation(
            on_hand=on_hand,
            on_order=on_order,
            daily_avg=result.daily_avg,
            lead_time_days=lead,
            safety_stock=safety,
            horizon_days=30,
        )

        # Upsert
        forecast = self.env["wms.forecast"].search(
            [("product_id", "=", product.id)], limit=1,
        )
        vals = {
            "product_id": product.id,
            "horizon_days": 30,
            "predicted_qty": result.predicted_qty,
            "daily_avg": result.daily_avg,
            "monthly_avg": result.monthly_avg,
            "reorder_qty": reorder_qty,
            "reorder_date": reorder_date.date() if reorder_date else False,
            "velocity_class": result.velocity_class,
            "is_consumable": product.type == "consu",
            "last_trained": fields.Datetime.now(),
            "model_name": result.model_name,
            "rmse": result.rmse,
            "on_hand": on_hand,
            "lead_time_days": lead,
            "safety_stock": safety,
            "note": note,
        }
        if forecast:
            forecast.write(vals)
        else:
            forecast = self.env["wms.forecast"].create(vals)

        self.env["wms.forecast.history"].create({
            "product_id": product.id,
            "model_name": result.model_name,
            "predicted_qty": result.predicted_qty,
            "rmse": result.rmse,
            "velocity_class": result.velocity_class,
        })
        return forecast

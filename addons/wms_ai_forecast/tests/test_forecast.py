"""High - forecast engine fixes:

* ``is_consumable`` is keyed off real movement history, not the retired
  ``product.type`` (which reports ``consu`` for every storable in Odoo 19, so the
  old test was always true);
* nightly training prefetches on-hand / on-order / safety-stock in grouped
  queries instead of N+1 per-product searches;
* forecast-history is bounded by a retention window.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_forecast")
class TestForecastEngine(TransactionCase):
    def test_run_all_forecasts_no_history_is_monitor_only(self):
        product = self.env["product.product"].create(
            {"name": "Forecast Storable", "is_storable": True}
        )
        self.env["wms.forecast.engine"].run_all_forecasts()
        fc = self.env["wms.forecast"].search([("product_id", "=", product.id)])
        self.assertTrue(fc, "a forecast row should exist for every storable product")
        # No outflow history -> dead + not consumable. The old
        # `product.type == 'consu'` test would have set is_consumable=True here.
        self.assertEqual(fc.velocity_class, "dead")
        self.assertFalse(fc.is_consumable)

    def test_history_retention_prunes_old_rows(self):
        product = self.env["product.product"].create(
            {"name": "Forecast Retention", "is_storable": True}
        )
        Hist = self.env["wms.forecast.history"]
        old = Hist.create(
            {
                "product_id": product.id,
                "trained_at": fields.Datetime.now() - timedelta(days=400),
                "model_name": "old",
            }
        )
        recent = Hist.create(
            {
                "product_id": product.id,
                "trained_at": fields.Datetime.now() - timedelta(days=5),
                "model_name": "recent",
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "wms_ai_forecast.history_retention_days", "365"
        )
        self.env["wms.forecast.engine"]._prune_history()
        self.assertFalse(old.exists(), "history older than the window must be pruned")
        self.assertTrue(recent.exists(), "recent history must be kept")

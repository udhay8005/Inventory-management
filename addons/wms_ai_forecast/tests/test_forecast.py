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

    def test_history_trained_at_indexed(self):
        # trained_at is the _order key and the prune-filter column; it must be
        # indexed so neither does a full sequential scan as history grows.
        self.assertTrue(
            self.env["wms.forecast.history"]._fields["trained_at"].index,
            "wms.forecast.history.trained_at must be indexed",
        )

    def test_outflow_counts_scan_issue_to_internal_sink(self):
        """A Scan Issue routes stock into the INTERNAL 'Trust internal use'
        sink, not to a customer/production location — that is the trust's only
        consumption path. The engine must observe it as outflow, and on-hand
        must EXCLUDE the sink (already-consumed goods).

        Regression for the old query, which filtered destination usage IN
        ('customer','production') and therefore saw zero outflow for every
        product, leaving the AI buying recommendation and low-stock alert
        permanently silent.
        """
        wh = self.env["stock.warehouse"].search([], limit=1)
        stock = wh.lot_stock_id
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "FC Keeper"})
        dept = self.env.ref("wms_location.dept_other")
        # consumable kind -> Units UoM (counted) so the photo gate stays off and
        # the issue validates inline; cheap so the high-value gate never trips.
        product = self.env["product.product"].create(
            {
                "name": "FC Bran",
                "type": "consu",
                "is_storable": True,
                "barcode": "FCBRAN1",
                "wms_product_kind": "consumable",
                "standard_price": 1.0,
            }
        )
        self.env["stock.quant"]._update_available_quantity(product, stock, 100.0)

        engine = self.env["wms.forecast.engine"]
        self.assertFalse(engine._gather_outflow(product), "no issues yet -> no outflow")

        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": wh.id,
                "requested_qty": 10.0,
                "last_scan": "FCBRAN1",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "forecast outflow test",
                "storekeeper_id": keeper.id,
                "department_id": dept.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        self.assertTrue(wiz.picking_id and wiz.picking_id.state == "done")

        outflow = engine._gather_outflow(product)
        self.assertTrue(outflow, "a Scan Issue to the internal sink must register as outflow")
        self.assertAlmostEqual(sum(qty for _d, qty in outflow), 10.0, places=3)

        # On-hand = warehouse storage only (100 received - 10 issued = 90); the
        # 10 sitting in the consumed-goods sink must NOT be counted as on-hand.
        self.assertAlmostEqual(engine._on_hand(product), 90.0, places=3)

        # The whole downstream chain now treats it as consumable, not 'dead'.
        engine.run_all_forecasts()
        fc = self.env["wms.forecast"].search([("product_id", "=", product.id)])
        self.assertTrue(
            fc.is_consumable, "a product with scan-issue history must be flagged consumable"
        )

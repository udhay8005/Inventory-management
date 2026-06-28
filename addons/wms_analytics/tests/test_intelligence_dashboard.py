"""Wave 2 #1 — Intelligence KPI dashboard: renders for a manager, 404 otherwise,
and the KPI aggregation computes correct values."""

from datetime import timedelta

from odoo import fields
from odoo.addons.wms_analytics.controllers.main import WmsIntelligenceDashboard
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestKpiValues(TransactionCase):
    """Value-level test of the KPI aggregation (controller._kpis), not just HTTP."""

    def test_kpis_reflect_seeded_state(self):
        env = self.env
        wh = env["stock.warehouse"].search([], limit=1)
        floor = env["stock.location"].create(
            {
                "name": "KPI Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        med = env["product.product"].create(
            {
                "name": "KPI Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "KPIMED01",
            }
        )
        healthy = env["stock.lot"].create(
            {
                "name": "KPI-HEALTHY",
                "product_id": med.id,
                "company_id": env.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=400),
            }
        )
        recalled = env["stock.lot"].create(
            {
                "name": "KPI-RECALL",
                "product_id": med.id,
                "company_id": env.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=400),
                "wms_lot_state": "recalled",
            }
        )
        env["stock.quant"]._update_available_quantity(med, floor, 30, lot_id=healthy)
        env["stock.quant"]._update_available_quantity(med, floor, 10, lot_id=recalled)
        env.flush_all()

        k = WmsIntelligenceDashboard()._kpis(env)
        self.assertGreaterEqual(k["total_on_hand"], 40, "both lots' stock counts as on-hand")
        self.assertGreaterEqual(k["recalled"], 10, "recalled lot quantity surfaces in the KPI")
        self.assertLess(k["health_score"], 100.0, "a recalled lot drags the health score below 100")
        self.assertIn("inventory_value", k)
        self.assertEqual(k["risk_critical"] >= 0, True)


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestIntelligenceDashboard(HttpCase):
    def test_dashboard_renders_for_manager(self):
        self.env["res.users"].create(
            {
                "name": "INTEL Manager",
                "login": "intel_mgr",
                "password": "intel_mgr",
                "group_ids": [(4, self.env.ref("wms_location.group_wms_manager").id)],
            }
        )
        self.authenticate("intel_mgr", "intel_mgr")
        r = self.url_open("/wms/intelligence")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Warehouse Intelligence", body)
        # A few representative KPI tiles must be present.
        for label in ("Total inventory", "Near expiry", "Stock health", "Expiry risk: critical"):
            self.assertIn(label, body, "KPI tile missing: %s" % label)

    def test_dashboard_blocked_for_non_manager(self):
        self.env["res.users"].create(
            {
                "name": "INTEL User",
                "login": "intel_user",
                "password": "intel_user",
                "group_ids": [(4, self.env.ref("wms_location.group_wms_user").id)],
            }
        )
        self.authenticate("intel_user", "intel_user")
        r = self.url_open("/wms/intelligence")
        self.assertEqual(r.status_code, 404, "non-managers must not reach the KPI dashboard")

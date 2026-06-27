"""Wave 2 #1 — Intelligence KPI dashboard: renders for a manager, 404 otherwise."""

from odoo.tests import HttpCase, tagged


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

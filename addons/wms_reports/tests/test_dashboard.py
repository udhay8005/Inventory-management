"""P1 - the executive dashboard (/wms/dashboard) must render for a manager and
be hidden from non-managers. Smoke the controller end-to-end so the reused
report search_counts + _health_snapshot() path is exercised, not just the data.
"""

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_dashboard")
class TestDashboard(HttpCase):
    def test_dashboard_renders_for_manager(self):
        # Admin needs the WMS manager capability to pass the controller gate.
        manager = self.env.ref("wms_location.group_wms_manager")
        self.env.ref("base.user_admin").write({"group_ids": [(4, manager.id)]})
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/dashboard")
        self.assertEqual(resp.status_code, 200)
        # Core sections are present.
        self.assertIn("Warehouse Dashboard", resp.text)
        self.assertIn("System health", resp.text)
        self.assertIn("Stock totals", resp.text)
        self.assertIn("Needs attention", resp.text)
        self.assertIn("Receipts", resp.text)  # today's-activity row label

    def test_dashboard_blocked_for_non_manager(self):
        # A brand-new internal user with no WMS groups must be denied (404).
        user = self.env["res.users"].create(
            {
                "name": "Plain User",
                "login": "plain_dash_user",
                "password": "plain_dash_user_pw",
            }
        )
        self.assertFalse(user.has_group("wms_location.group_wms_manager"))
        self.authenticate("plain_dash_user", "plain_dash_user_pw")
        resp = self.url_open("/wms/dashboard")
        self.assertEqual(resp.status_code, 404)

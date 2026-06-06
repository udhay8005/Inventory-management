"""Batch 6 — low-stock alert.

The daily cron must notify WMS managers in-app (Discuss) about products at or
below their reorder level, and must stay quiet when nothing needs ordering. The
optional email path is best-effort and must never break the run.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_alert")
class TestLowStockAlert(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_group = cls.env.ref("wms_location.group_wms_manager")
        cls.admin = cls.env.ref("base.user_admin")
        cls.admin.write({"group_ids": [(4, cls.manager_group.id)]})
        cls.product = cls.env["product.product"].create(
            {
                "name": "ALERT Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "ALERTTEST1",
                "wms_product_kind": "consumable",
            }
        )

    def _manager_inbox(self):
        """Inbox notifications delivered to the admin manager — proves the
        alert truly surfaces (Discuss Inbox / systray), not just a chatter log."""
        return self.env["mail.notification"].search(
            [("res_partner_id", "=", self.admin.partner_id.id)]
        )

    def test_alert_notifies_managers_in_app(self):
        self.env["wms.forecast"].create({"product_id": self.product.id, "reorder_qty": 7.0})
        self.env.flush_all()
        self.env["wms.stock.alert"]._cron_check_low_stock()
        notifs = self._manager_inbox()
        self.assertTrue(
            any("ALERT Widget" in (n.mail_message_id.body or "") for n in notifs),
            "a manager should receive a low-stock notification in their inbox",
        )

    def test_quiet_when_nothing_low(self):
        # Neutralise any pre-existing low forecasts so the assertion is about
        # THIS test's state, not whatever the database happened to carry.
        self.env["wms.forecast"].sudo().search([("reorder_qty", ">", 0)]).write(
            {"reorder_qty": 0.0}
        )
        self.env.flush_all()
        before = len(self._manager_inbox())
        self.env["wms.stock.alert"]._cron_check_low_stock()
        self.assertEqual(len(self._manager_inbox()), before, "no products low -> no alert")

    def test_email_enabled_path_does_not_crash(self):
        # With the email channel on but no SMTP, the in-app notice must still
        # deliver and the cron must complete (email is best-effort).
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.alert_email", "1")
        self.env["wms.forecast"].create({"product_id": self.product.id, "reorder_qty": 4.0})
        self.env.flush_all()
        self.env["wms.stock.alert"]._cron_check_low_stock()
        notifs = self._manager_inbox()
        self.assertTrue(any("ALERT Widget" in (n.mail_message_id.body or "") for n in notifs))
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.alert_email", "0")

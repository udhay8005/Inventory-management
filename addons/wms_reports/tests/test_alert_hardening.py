"""Quick-win C - alert hardening.

Every alert now reaches managers in their Discuss Inbox (the existing partner.
message_post pattern delivered ZERO inbox notifications - users don't follow
their own contact). Two new alerts close the silent-failure gaps:

  * Restore-drill failure -> immediate manager notice.
  * Health CRITICAL       -> escalation cron (every 4h, idempotent).

Email is optional (System Parameter wms_reports.alert_email).
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_alert_hardening")
class TestAlertHardening(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        manager = cls.env.ref("wms_location.group_wms_manager")
        cls.admin = cls.env.ref("base.user_admin")
        cls.admin.write({"group_ids": [(4, manager.id)]})

    def _inbox(self):
        return self.env["mail.notification"].search(
            [("res_partner_id", "=", self.admin.partner_id.id)]
        )

    def test_backup_notify_lands_in_inbox(self):
        """The old partner.message_post never created inbox notifications;
        the shared helper now does."""
        before = len(self._inbox())
        self.env["wms.backup.audit"]._notify_managers("CRITICAL", "disk full")
        self.assertGreater(
            len(self._inbox()),
            before,
            "backup-health alert must land in the manager's inbox",
        )

    def test_restore_drill_failure_alerts_and_dedupes(self):
        # A failed drill row, not yet notified.
        row = (
            self.env["wms.backup.audit"]
            .sudo()
            .create(
                {
                    "name": "drill-fail-test",
                    "audit_type": "restore_drill",
                    "success": False,
                    "message": "pg_restore TOC mismatch",
                    "host": "test-host",
                }
            )
        )
        before = len(self._inbox())
        self.env["wms.backup.audit"]._cron_check_restore_drill()
        self.assertGreater(len(self._inbox()), before, "restore failure must alert")
        self.assertTrue(row.notified, "row should be marked notified")
        # Second pass must not re-alert.
        mid = len(self._inbox())
        self.env["wms.backup.audit"]._cron_check_restore_drill()
        self.assertEqual(len(self._inbox()), mid, "no repeat alert for the same row")

    def test_health_critical_escalation_idempotent(self):
        Audit = self.env["wms.backup.audit"]
        before = Audit.sudo().search_count([("audit_type", "=", "health_critical")])
        # The fresh DB has no successful backup, so health is CRITICAL.
        Audit._cron_escalate_health_critical()
        after = Audit.sudo().search_count([("audit_type", "=", "health_critical")])
        self.assertEqual(
            after,
            before + 1,
            "health-critical escalation must record one audit row",
        )
        # A second run within 20h must NOT create another row.
        Audit._cron_escalate_health_critical()
        self.assertEqual(
            Audit.sudo().search_count([("audit_type", "=", "health_critical")]),
            before + 1,
            "no repeat escalation within the 20h dedupe window",
        )

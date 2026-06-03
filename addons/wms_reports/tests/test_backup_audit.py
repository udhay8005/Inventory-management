# -*- coding: utf-8 -*-
"""Tests for the observability foundations added in wms_reports 19.0.2.0.0:
the wms.backup.audit model, its _health_snapshot() logic, the staleness
cron, and the /wms/health endpoint.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_health")
class TestBackupAuditModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]

    def _mk(self, audit_type, success, ago_hours, **extra):
        vals = {
            "name": "test-%s" % audit_type,
            "audit_type": audit_type,
            "success": success,
            "event_time": fields.Datetime.now() - timedelta(hours=ago_hours),
        }
        vals.update(extra)
        return self.Audit.create(vals)

    def test_snapshot_healthy_with_fresh_backup_and_drill(self):
        self._mk("backup_db", True, 1)
        self._mk("restore_drill", True, 24)
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "HEALTHY")
        self.assertTrue(snap["db_reachable"])
        self.assertIsNotNone(snap["last_backup_age_hours"])

    def test_snapshot_critical_with_no_backup(self):
        # Fresh DB has zero audit rows → no successful backup → CRITICAL.
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "CRITICAL")
        self.assertTrue(any("backup" in w for w in snap["warnings"]))

    def test_snapshot_degraded_with_stale_backup(self):
        self._mk("backup_db", True, 48)  # > 24h
        self._mk("restore_drill", True, 24)
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "DEGRADED")
        self.assertTrue(any("backup" in w for w in snap["warnings"]))

    def test_snapshot_degraded_when_drill_missing(self):
        self._mk("backup_db", True, 1)  # backup fresh, but no drill
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "DEGRADED")
        self.assertTrue(any("drill" in w for w in snap["warnings"]))

    def test_failed_backup_not_counted_as_success(self):
        self._mk("backup_db", False, 1)  # recent but FAILED
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "CRITICAL")

    def test_last_success_ignores_failures(self):
        self._mk("backup_db", False, 1)
        ok = self._mk("backup_db", True, 5)
        self.assertEqual(self.Audit._last_success("backup_db"), ok)

    def test_freshness_cron_records_warning_when_stale(self):
        self._mk("backup_db", True, 48)
        before = self.Audit.search_count([("audit_type", "=", "staleness_warning")])
        self.Audit._cron_check_backup_freshness()
        after = self.Audit.search_count([("audit_type", "=", "staleness_warning")])
        self.assertGreater(after, before)

    def test_freshness_cron_quiet_when_healthy(self):
        self._mk("backup_db", True, 1)
        self._mk("restore_drill", True, 24)
        before = self.Audit.search_count([("audit_type", "=", "staleness_warning")])
        self.Audit._cron_check_backup_freshness()
        after = self.Audit.search_count([("audit_type", "=", "staleness_warning")])
        self.assertEqual(after, before)


@tagged("post_install", "-at_install", "wms", "wms_health")
class TestHealthEndpoint(HttpCase):
    def test_health_endpoint_returns_json(self):
        # auth="public" → no login needed. Fresh test DB has no backups,
        # so we expect CRITICAL (503), but accept any valid status code.
        resp = self.url_open("/wms/health")
        self.assertIn(resp.status_code, (200, 503))
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn(data["status"], ("HEALTHY", "DEGRADED", "CRITICAL"))
        # Must never leak internals.
        self.assertNotIn("traceback", str(data).lower())

    def test_health_endpoint_no_secret_leak(self):
        resp = self.url_open("/wms/health")
        body = resp.text.lower()
        for forbidden in ("password", "passphrase", "secret", "pgpassword"):
            self.assertNotIn(forbidden, body)

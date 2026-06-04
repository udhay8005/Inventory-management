"""Critical #8 - /wms/health probes reality (live DB, backup-file-on-disk,
disk space) instead of trusting the audit table alone."""

import os
import shutil
import tempfile

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_health")
class TestHealthProbe(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.tmp = tempfile.mkdtemp(prefix="wms_health_test_")
        cls.env["ir.config_parameter"].sudo().set_param("wms_reports.backup_dir", cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def _backup_row(self, filename):
        return self.Audit.sudo().create(
            {
                "name": filename,
                "audit_type": "backup_db",
                "success": True,
                "verified": True,
            }
        )

    def test_db_reachable_is_a_real_probe(self):
        snap = self.Audit._health_snapshot()
        self.assertTrue(snap["db_reachable"])

    def test_missing_backup_file_is_critical(self):
        self._backup_row("does-not-exist.dump.gpg")
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "CRITICAL")
        self.assertFalse(snap["backup_file_present"])

    def test_present_backup_file_is_not_critical_for_that_reason(self):
        fname = "present.dump.gpg"
        with open(os.path.join(self.tmp, fname), "wb") as fh:
            fh.write(b"x")
        # A recent drill too, so the drill-age check doesn't drag status down.
        self.Audit.sudo().create({"name": "drill", "audit_type": "restore_drill", "success": True})
        self._backup_row(fname)
        snap = self.Audit._health_snapshot()
        self.assertTrue(snap["backup_file_present"])
        self.assertNotEqual(snap["status"], "CRITICAL")

# -*- coding: utf-8 -*-
"""Tests for the Google Drive backup integration (wms_reports 19.0.3.0.0).

Scope:

  * wms.gdrive.backup catalog model — record_set() door, defaults, the
    exact column contract shared with Write-GDriveCatalogRow in
    scripts/gdrive-lib.ps1 (psql writes bypass the ORM);
  * wms.backup.audit audit_type gains backup_gdrive / restore_gdrive;
  * the seeded wms_gdrive.* ir.config_parameter defaults;
  * the group_wms_backup_now capability group wiring + wizard ACLs;
  * the Backup Now wizard (D5 schtasks trigger + audit-row polling,
    deterministic via the test_skip_schtasks seam / subprocess stubs);
  * the settings wizard (param round-trip, validation, gdrive-test.ps1
    JSON parsing, best-effort Apply Schedule);
  * the _health_snapshot() Drive fields (P13) in every state — disabled,
    dark, fresh, stale, auth-expired, storage-full — and the rule that
    Drive problems are DEGRADED-level only, NEVER CRITICAL;
  * the two crons: _cron_check_gdrive_freshness (20h dedupe) and
    _cron_notify_gdrive_events (notified-flag dedupe, notify_success /
    notify_failure switches), with notify_wms_managers mocked.
"""
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.wms_reports.models import wms_backup_audit as audit_module
from odoo.addons.wms_reports.wizard import wms_gdrive_backup_now as backup_now_wizard
from odoo.addons.wms_reports.wizard import wms_gdrive_settings as settings_wizard
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

# The column contract paired with Write-GDriveCatalogRow in
# scripts/gdrive-lib.ps1. The script UPSERTs these columns via psql,
# bypassing the ORM — any rename/addition must update the model, the
# script, and this list in the same commit (see the model docstring).
CATALOG_COLUMNS = [
    "name",
    "set_stamp",
    "db_name",
    "backup_type",
    "backup_time",
    "year",
    "month_label",
    "day",
    "drive_name",
    "drive_file_id",
    "drive_folder",
    "filestore_drive_id",
    "size_mb",
    "checksum",
    "uploaded",
    "upload_time",
    "creator",
    "encrypted",
    "wms_version",
    "info_json",
    "restored_count",
]

# Non-blank defaults seeded by data/gdrive_params.xml (section 2.3 of the
# spec). last_about / last_manual_requester seed as '' and are asserted
# separately (get_param coalesces '' to its default).
PARAM_DEFAULTS = {
    "wms_gdrive.enabled": "1",
    "wms_gdrive.manual_enabled": "1",
    "wms_gdrive.backup_time": "16:30",
    "wms_gdrive.notify_success": "1",
    "wms_gdrive.notify_failure": "1",
    "wms_gdrive.retention_daily_days": "30",
    "wms_gdrive.retention_weekly_months": "6",
    "wms_gdrive.retention_monthly_years": "2",
    "wms_gdrive.delete_manual": "0",
    "wms_gdrive.folder_name": "Inventory_Backups",
}


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveCatalogModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Catalog = cls.env["wms.gdrive.backup"]

    def _set_vals(self, **extra):
        """A full catalog row exactly as the script's success-path UPSERT
        writes it (every contract column populated)."""
        vals = {
            "name": "wms-20260612-163000.dump.gpg",
            "set_stamp": "20260612-163000",
            "db_name": "wms",
            "backup_type": "auto",
            "backup_time": fields.Datetime.now(),
            "year": "2026",
            "month_label": "06-June",
            "day": "2026-06-12",
            "drive_name": "WMS_DB_2026-06-12_16-30-00.dump.gpg",
            "drive_file_id": "drive-file-id-db",
            "drive_folder": "Inventory_Backups/2026/06-June/2026-06-12",
            "filestore_drive_id": "drive-file-id-fs",
            "size_mb": 50.0,
            "checksum": "a" * 64,
            "uploaded": True,
            "upload_time": fields.Datetime.now(),
            "creator": "system (scheduled)",
            "encrypted": True,
            "wms_version": "19.0.3.0.0",
            "info_json": '{"schema_version": 1}',
            "restored_count": 0,
        }
        vals.update(extra)
        return vals

    def test_record_set_creates_full_row(self):
        rec = self.Catalog.record_set(self._set_vals())
        self.assertTrue(rec.exists())
        self.assertEqual(rec.name, "wms-20260612-163000.dump.gpg")
        self.assertEqual(rec.set_stamp, "20260612-163000")
        self.assertEqual(rec.drive_name, "WMS_DB_2026-06-12_16-30-00.dump.gpg")
        self.assertEqual(rec.checksum, "a" * 64)
        self.assertTrue(rec.uploaded)

    def test_defaults_match_pending_failure_row(self):
        # The script's Stage-5 failure path writes a minimal pending row;
        # the ORM defaults must agree with the script's expectations.
        rec = self.Catalog.record_set({"name": "wms-20260612-163000.dump.gpg"})
        self.assertEqual(rec.backup_type, "auto")
        self.assertFalse(rec.uploaded)
        self.assertTrue(rec.encrypted)
        self.assertEqual(rec.restored_count, 0)

    def test_column_contract_fields_exist(self):
        for col in CATALOG_COLUMNS:
            self.assertIn(
                col,
                self.Catalog._fields,
                "catalog column %r missing — Write-GDriveCatalogRow "
                "(scripts/gdrive-lib.ps1) writes it via psql" % col,
            )

    def test_contract_columns_are_plain_stored(self):
        # psql writes bypass the ORM: a compute/related on any contract
        # column would silently diverge from what the script writes.
        for col in CATALOG_COLUMNS:
            field = self.Catalog._fields[col]
            self.assertTrue(field.store, "contract column %r must be stored" % col)
            self.assertFalse(field.compute, "contract column %r must not be computed" % col)
            self.assertFalse(field.related, "contract column %r must not be related" % col)

    def test_ordering_newest_backup_first(self):
        old = self.Catalog.record_set(
            self._set_vals(
                set_stamp="20260611-163000",
                backup_time=fields.Datetime.now() - timedelta(days=1),
            )
        )
        new = self.Catalog.record_set(self._set_vals())
        found = self.Catalog.search([("id", "in", (old | new).ids)])
        self.assertEqual(found[0], new, "_order must put the newest backup first")


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveAuditTypes(TransactionCase):
    def test_selection_contains_gdrive_keys(self):
        selection = dict(self.env["wms.backup.audit"]._fields["audit_type"].selection)
        self.assertEqual(selection.get("backup_gdrive"), "Google Drive upload")
        self.assertEqual(selection.get("restore_gdrive"), "Google Drive restore")

    def test_record_event_accepts_gdrive_types(self):
        Audit = self.env["wms.backup.audit"]
        for audit_type in ("backup_gdrive", "restore_gdrive"):
            row = Audit.record_event(
                {
                    "name": "wms-20260612-163000.dump.gpg",
                    "audit_type": audit_type,
                    "success": True,
                }
            )
            self.assertEqual(row.audit_type, audit_type)
            self.assertTrue(row.success)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveParams(TransactionCase):
    def test_params_seeded_with_defaults(self):
        Param = self.env["ir.config_parameter"].sudo()
        for key, default in PARAM_DEFAULTS.items():
            self.assertEqual(
                Param.get_param(key),
                default,
                "%s must be seeded to %r by data/gdrive_params.xml" % (key, default),
            )

    def test_blank_state_params_exist(self):
        # Seeded as '' so the keys exist for the script/wizard handshake;
        # get_param('') falls back to its default, so probe the rows.
        Param = self.env["ir.config_parameter"].sudo()
        for key in ("wms_gdrive.last_about", "wms_gdrive.last_manual_requester"):
            self.assertTrue(
                Param.search_count([("key", "=", key)]),
                "%s must be seeded (blank) by data/gdrive_params.xml" % key,
            )


class GdriveUsersMixin:
    """Shared user factory + ACL probe (test_acl_capability.py pattern)."""

    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "group_ids": [(6, 0, [self.env.ref(xmlid).id])]}
        )

    def _can(self, user, model, mode):
        return self.env["ir.model.access"].with_user(user).check(model, mode, raise_exception=False)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveCapabilityGroup(GdriveUsersMixin, TransactionCase):
    """D11: one keeper power = one capability sub-group. Backup Now is the
    ONLY surface the capability opens; catalog / settings / audit stay
    manager-only (P7: restore completely hidden from keepers)."""

    def test_backup_now_implies_wms_user(self):
        cap = self.env.ref("wms_reports.group_wms_backup_now")
        self.assertIn(self.env.ref("wms_location.group_wms_user"), cap.implied_ids)

    def test_manager_implies_backup_now(self):
        mgr = self.env.ref("wms_location.group_wms_manager")
        self.assertIn(self.env.ref("wms_reports.group_wms_backup_now"), mgr.implied_ids)

    def test_backup_now_wizard_acl(self):
        base = self._user("wms_location.group_wms_user", "gd_acl_base")
        cap = self._user("wms_reports.group_wms_backup_now", "gd_acl_cap")
        mgr = self._user("wms_location.group_wms_manager", "gd_acl_mgr")
        model = "wms.gdrive.backup.now"
        self.assertFalse(self._can(base, model, "create"), "baseline keeper blocked")
        self.assertTrue(self._can(cap, model, "create"), "capability keeper allowed")
        self.assertTrue(self._can(mgr, model, "create"), "manager allowed via implication")

    def test_settings_and_catalog_stay_manager_only(self):
        cap = self._user("wms_reports.group_wms_backup_now", "gd_acl_cap2")
        mgr = self._user("wms_location.group_wms_manager", "gd_acl_mgr2")
        self.assertFalse(self._can(cap, "wms.gdrive.settings", "read"))
        self.assertFalse(self._can(cap, "wms.gdrive.backup", "read"))
        self.assertFalse(self._can(cap, "wms.backup.audit", "read"))
        self.assertTrue(self._can(mgr, "wms.gdrive.settings", "read"))
        self.assertTrue(self._can(mgr, "wms.gdrive.backup", "read"))
        # The catalog ACL is read-only even for managers (1,0,0,0): rows
        # are written by the script via psql, never from the UI.
        for mode in ("write", "create", "unlink"):
            self.assertFalse(self._can(mgr, "wms.gdrive.backup", mode))


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveBackupNowWizard(GdriveUsersMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cap_user = cls.env["res.users"].create(
            {
                "name": "gd_now_keeper",
                "login": "gd_now_keeper",
                "group_ids": [(6, 0, [cls.env.ref("wms_reports.group_wms_backup_now").id])],
            }
        )
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Audit = cls.env["wms.backup.audit"]

    def _wizard(self, user=None, skip=True):
        wizard = self.env["wms.gdrive.backup.now"]
        if user is not None:
            wizard = wizard.with_user(user)
        if skip:
            wizard = wizard.with_context(test_skip_schtasks=True)
        return wizard.create({})

    def test_backup_now_sets_running_and_requester_handshake(self):
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        self.assertEqual(wiz.state, "running")
        self.assertTrue(wiz.requested_at)
        handshake = self.Param.get_param("wms_gdrive.last_manual_requester")
        self.assertTrue(
            handshake.startswith(self.cap_user.login + "|"),
            "D5 handshake must be '<login>|<iso-ts>' (got %r)" % handshake,
        )

    def test_backup_now_blocked_when_manual_disabled(self):
        self.Param.set_param("wms_gdrive.manual_enabled", "0")
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        self.assertEqual(wiz.state, "failed")
        self.assertIn("turned off", wiz.result_html)

    def test_baseline_keeper_cannot_open_wizard(self):
        base = self._user("wms_location.group_wms_user", "gd_now_base")
        with self.assertRaises(AccessError):
            self._wizard(base)

    def test_graceful_when_schtasks_binary_absent(self):
        # No skip seam: the subprocess layer is stubbed to behave like a
        # host without schtasks.exe. Friendly message, no raw exception.
        wiz = self._wizard(self.cap_user, skip=False)
        with patch.object(
            backup_now_wizard.subprocess, "run", side_effect=FileNotFoundError("schtasks.exe")
        ):
            wiz.action_backup_now()
        self.assertEqual(wiz.state, "failed")
        self.assertIn("install-backup-tasks.ps1", wiz.result_html)
        self.assertNotIn("FileNotFoundError", wiz.result_html)

    def test_graceful_when_task_not_registered(self):
        # schtasks runs but the "WMS Manual Backup" task does not exist
        # (installer never re-run): rc != 0 -> degraded message with the
        # install hint; raw stderr stays out of the keeper-facing HTML.
        wiz = self._wizard(self.cap_user, skip=False)
        fake = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=b"",
            stderr=b"ERROR: The system cannot find the file specified.",
        )
        with patch.object(backup_now_wizard.subprocess, "run", return_value=fake):
            wiz.action_backup_now()
        self.assertEqual(wiz.state, "failed")
        self.assertIn("install-backup-tasks.ps1", wiz.result_html)
        self.assertNotIn("cannot find the file", wiz.result_html)

    def test_refresh_reports_file_size_and_drive_name(self):
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        local_name = "wms-20260612-170000.dump.gpg"
        self.Audit.record_event(
            {"name": local_name, "audit_type": "backup_db", "success": True, "size_mb": 42.5}
        )
        self.Audit.record_event(
            {"name": local_name, "audit_type": "backup_gdrive", "success": True}
        )
        self.env["wms.gdrive.backup"].record_set(
            {
                "name": local_name,
                "set_stamp": "20260612-170000",
                "drive_name": "WMS_DB_2026-06-12_17-00-00.dump.gpg",
                "uploaded": True,
            }
        )
        wiz.action_refresh()
        self.assertEqual(wiz.state, "done")
        self.assertIn(local_name, wiz.result_html)
        self.assertIn("42.5", wiz.result_html)
        self.assertIn("WMS_DB_2026-06-12_17-00-00.dump.gpg", wiz.result_html)

    def test_refresh_drive_failure_is_soft(self):
        # Local backup OK + Drive upload failed -> still "done": the local
        # artifact is THE backup, Drive retries on the next run (P14).
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        local_name = "wms-20260612-170100.dump.gpg"
        self.Audit.record_event(
            {"name": local_name, "audit_type": "backup_db", "success": True, "size_mb": 10.0}
        )
        self.Audit.record_event(
            {"name": local_name, "audit_type": "backup_gdrive", "success": False}
        )
        wiz.action_refresh()
        self.assertEqual(wiz.state, "done")
        self.assertIn("retried automatically", wiz.result_html)
        self.assertIn("local backup is safe", wiz.result_html)

    def test_refresh_local_failure_is_plain_language(self):
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        self.Audit.record_event(
            {
                "name": "wms-20260612-170200.dump.gpg",
                "audit_type": "backup_db",
                "success": False,
                "message": "Traceback (most recent call last): raw script detail",
            }
        )
        wiz.action_refresh()
        self.assertEqual(wiz.state, "failed")
        self.assertNotIn("Traceback", wiz.result_html)
        self.assertIn("Backup", wiz.result_html)

    def test_refresh_without_rows_stays_running(self):
        wiz = self._wizard(self.cap_user)
        wiz.action_backup_now()
        wiz.action_refresh()
        self.assertEqual(wiz.state, "running")
        self.assertIn("few minutes", wiz.result_html)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveSettingsWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Wizard = cls.env["wms.gdrive.settings"]

    def test_default_get_loads_params(self):
        self.Param.set_param("wms_gdrive.enabled", "0")
        self.Param.set_param("wms_gdrive.backup_time", "17:45")
        self.Param.set_param("wms_gdrive.retention_daily_days", "45")
        self.Param.set_param("wms_gdrive.folder_name", "Trust_Backups")
        wiz = self.Wizard.create({})
        self.assertFalse(wiz.enabled)
        self.assertEqual(wiz.backup_time, "17:45")
        self.assertEqual(wiz.retention_daily_days, 45)
        self.assertEqual(wiz.folder_name, "Trust_Backups")
        self.assertTrue(wiz.manual_enabled, "untouched keys keep their seeded default")

    def test_save_round_trips_params(self):
        wiz = self.Wizard.create({})
        wiz.write(
            {
                "enabled": False,
                "manual_enabled": True,
                "backup_time": "06:15",
                "retention_daily_days": 10,
                "retention_weekly_months": 3,
                "retention_monthly_years": 1,
                "delete_manual": True,
                "folder_name": "Trust_Backups",
            }
        )
        wiz.action_save()
        self.assertEqual(self.Param.get_param("wms_gdrive.enabled"), "0")
        self.assertEqual(self.Param.get_param("wms_gdrive.manual_enabled"), "1")
        self.assertEqual(self.Param.get_param("wms_gdrive.backup_time"), "06:15")
        self.assertEqual(self.Param.get_param("wms_gdrive.retention_daily_days"), "10")
        self.assertEqual(self.Param.get_param("wms_gdrive.retention_weekly_months"), "3")
        self.assertEqual(self.Param.get_param("wms_gdrive.retention_monthly_years"), "1")
        self.assertEqual(self.Param.get_param("wms_gdrive.delete_manual"), "1")
        self.assertEqual(self.Param.get_param("wms_gdrive.folder_name"), "Trust_Backups")

    def test_save_validates_retention_positive_ints(self):
        wiz = self.Wizard.create({})
        wiz.retention_daily_days = 0
        with self.assertRaises(UserError):
            wiz.action_save()

    def test_save_validates_backup_time_format(self):
        wiz = self.Wizard.create({})
        wiz.backup_time = "25:99"
        with self.assertRaises(UserError):
            wiz.action_save()

    def test_apply_schedule_persists_param(self):
        wiz = self.Wizard.with_context(test_skip_schtasks=True).create({})
        wiz.backup_time = "07:30"
        wiz.action_apply_schedule()
        self.assertEqual(self.Param.get_param("wms_gdrive.backup_time"), "07:30")
        self.assertIn("07:30", wiz.result_html)

    def test_apply_schedule_failure_shows_fallback_never_throws(self):
        wiz = self.Wizard.create({})
        wiz.backup_time = "07:35"
        with patch.object(
            settings_wizard.subprocess, "run", side_effect=FileNotFoundError("schtasks.exe")
        ):
            wiz.action_apply_schedule()  # must NOT raise
        self.assertIn("install-backup-tasks.ps1 -BackupAt", wiz.result_html)
        # Best-effort contract: the param is saved even when schtasks fails.
        self.assertEqual(self.Param.get_param("wms_gdrive.backup_time"), "07:35")

    def _stub_gdrive_test(self, stdout):
        """Stub the gdrive-test.ps1 subprocess: script path resolved to a
        file that certainly exists (this test file), one JSON stdout line."""
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")
        return (
            patch.object(
                settings_wizard.WmsGdriveSettings,
                "_gdrive_test_script_path",
                return_value=os.path.abspath(__file__),
            ),
            patch.object(settings_wizard.subprocess, "run", return_value=fake),
        )

    def test_test_connection_parses_json_and_renders_email(self):
        wiz = self.Wizard.create({})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": true, "email": "office.dakshinvrindavan@gmail.com",'
            b' "used_mb": 1024.0, "limit_mb": 15360.0, "folder_ok": true}'
        )
        with path_patch, run_patch:
            wiz.action_test_connection()
        self.assertIn("office.dakshinvrindavan@gmail.com", wiz.result_html)
        self.assertIn("Connected", wiz.result_html)

    def test_test_connection_auth_expired_instruction(self):
        wiz = self.Wizard.create({})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": false, "error": "GDRIVE_AUTH_EXPIRED: token refresh rejected",'
            b' "auth_expired": true}'
        )
        with path_patch, run_patch:
            wiz.action_test_connection()
        self.assertIn("setup-gdrive-auth.ps1", wiz.result_html)

    def test_test_upload_renders_roundtrip(self):
        wiz = self.Wizard.create({})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": true, "file": "connection-test-20260612.txt", "roundtrip_ms": 850}'
        )
        with path_patch, run_patch:
            wiz.action_test_upload()
        self.assertIn("connection-test-20260612.txt", wiz.result_html)
        self.assertIn("850", wiz.result_html)


class GdriveHealthMixin:
    """Audit-row seeding + a deterministic local-healthy baseline for the
    health / cron suites (test_backup_audit.py _mk pattern)."""

    def _mk(self, audit_type, success, ago_hours, **extra):
        vals = {
            "name": "test-%s" % audit_type,
            "audit_type": audit_type,
            "success": success,
            "event_time": fields.Datetime.now() - timedelta(hours=ago_hours),
        }
        vals.update(extra)
        return self.env["wms.backup.audit"].create(vals)

    def _seed_local_healthy(self):
        """Fresh local backup + drill, with the disk probes pointed at a
        guaranteed-absent directory so the file-presence / free-space
        checks stay neutral on any machine (the repo root has a real
        backups/ dir on the dev box; CI does not)."""
        self.env["ir.config_parameter"].sudo().set_param(
            "wms_reports.backup_dir",
            os.path.join(tempfile.gettempdir(), "wms_gdrive_absent_%s" % uuid.uuid4().hex),
        )
        self._mk("backup_db", True, 1)
        self._mk("restore_drill", True, 24)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveHealthSnapshot(GdriveHealthMixin, TransactionCase):
    """_health_snapshot() Drive fields (spec section 5.1) in every state,
    and the DEGRADED-never-CRITICAL contract for Drive problems."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.Param = cls.env["ir.config_parameter"].sudo()

    def test_stale_threshold_constant(self):
        self.assertEqual(audit_module.GDRIVE_STALE_HOURS, 26)

    def test_disabled_keeps_drive_fields_dark(self):
        # Kill-switch honored even with upload rows on record.
        self._seed_local_healthy()
        self.Param.set_param("wms_gdrive.enabled", "0")
        self._mk("backup_gdrive", True, 1)
        snap = self.Audit._health_snapshot()
        self.assertFalse(snap["gdrive_enabled"])
        for key in (
            "drive_connected",
            "last_upload_age_hours",
            "drive_storage_used_mb",
            "drive_storage_limit_mb",
            "next_backup_at",
        ):
            self.assertNotIn(key, snap, "%s must be absent when Drive is disabled" % key)
        self.assertEqual(
            snap["status"], "HEALTHY", "a disabled Drive stage must not degrade health"
        )

    def test_unconfigured_drive_stays_dark(self):
        # enabled (seeded default '1') but never set up: no upload rows,
        # blank last_about cache -> no Drive fields, no Drive warnings.
        self._seed_local_healthy()
        self.Param.set_param("wms_gdrive.last_about", "")
        snap = self.Audit._health_snapshot()
        self.assertFalse(snap["gdrive_enabled"])
        self.assertNotIn("drive_connected", snap)
        self.assertEqual(snap["status"], "HEALTHY")

    def test_enabled_fresh_upload_connected(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        snap = self.Audit._health_snapshot()
        self.assertTrue(snap["gdrive_enabled"])
        self.assertTrue(snap["drive_connected"])
        self.assertAlmostEqual(snap["last_upload_age_hours"], 1.0, delta=0.2)
        self.assertTrue(snap["next_backup_at"])
        self.assertEqual(snap["status"], "HEALTHY")
        self.assertFalse([w for w in snap["warnings"] if "Google Drive" in w])

    def test_stale_upload_degraded_never_critical(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 27)  # > GDRIVE_STALE_HOURS
        snap = self.Audit._health_snapshot()
        self.assertEqual(
            snap["status"],
            "DEGRADED",
            "Drive staleness is DEGRADED — CRITICAL is reserved for the local pipeline",
        )
        self.assertTrue(any("Google Drive upload is stale" in w for w in snap["warnings"]))
        self.assertFalse(snap["drive_connected"])

    def test_auth_expired_warning_from_newest_failure(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 30)
        self._mk(
            "backup_gdrive",
            False,
            2,
            message="Drive upload FAILED: GDRIVE_AUTH_EXPIRED: re-run "
            "scripts\\setup-gdrive-auth.ps1",
        )
        snap = self.Audit._health_snapshot()
        self.assertIn("Google Drive auth expired", snap["warnings"])
        self.assertEqual(snap["status"], "DEGRADED")

    def test_auth_warning_clears_after_reconsent(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", False, 5, message="GDRIVE_AUTH_EXPIRED: token rejected")
        self._mk("backup_gdrive", True, 1)  # newest row is a success again
        snap = self.Audit._health_snapshot()
        self.assertNotIn("Google Drive auth expired", snap["warnings"])
        self.assertEqual(snap["status"], "HEALTHY")

    def test_storage_above_90_percent_warns(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        self.Param.set_param(
            "wms_gdrive.last_about",
            json.dumps(
                {
                    "used_mb": 14000.0,
                    "limit_mb": 15360.0,
                    "checked_utc": "2026-06-12T10:00:00Z",
                    "email": "office.dakshinvrindavan@gmail.com",
                }
            ),
        )
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["drive_storage_used_mb"], 14000.0)
        self.assertEqual(snap["drive_storage_limit_mb"], 15360.0)
        self.assertTrue(any("storage above 90%" in w for w in snap["warnings"]))
        self.assertEqual(snap["status"], "DEGRADED")

    def test_connected_via_recent_about_probe(self):
        # No upload yet, but Test Connection cached a fresh about probe:
        # connected, with the no-successful-upload warning (DEGRADED).
        self._seed_local_healthy()
        checked = (fields.Datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.Param.set_param(
            "wms_gdrive.last_about",
            json.dumps({"used_mb": 100.0, "limit_mb": 15360.0, "checked_utc": checked}),
        )
        snap = self.Audit._health_snapshot()
        self.assertTrue(snap["gdrive_enabled"])
        self.assertTrue(snap["drive_connected"])
        self.assertIsNone(snap["last_upload_age_hours"])
        self.assertTrue(any("no successful Google Drive upload" in w for w in snap["warnings"]))
        self.assertEqual(snap["status"], "DEGRADED")

    def test_all_drive_issues_at_once_still_only_degraded(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 100)
        self._mk("backup_gdrive", False, 1, message="GDRIVE_AUTH_EXPIRED: re-consent")
        self.Param.set_param(
            "wms_gdrive.last_about",
            json.dumps(
                {"used_mb": 15000.0, "limit_mb": 15360.0, "checked_utc": "2026-01-01T00:00:00Z"}
            ),
        )
        snap = self.Audit._health_snapshot()
        drive_warnings = [w for w in snap["warnings"] if "Google Drive" in w]
        self.assertEqual(len(drive_warnings), 3, "stale + auth expired + storage")
        self.assertFalse(snap["drive_connected"])
        self.assertEqual(snap["status"], "DEGRADED")

    def test_next_backup_at_today_or_tomorrow(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        self.Param.set_param("wms_gdrive.backup_time", "16:30")

        def expected():
            # Same rule as the model: SERVER-LOCAL time (Task Scheduler
            # is the executor and runs in local time).
            now_local = datetime.now()
            cand = now_local.replace(hour=16, minute=30, second=0, microsecond=0)
            if cand <= now_local:
                cand += timedelta(days=1)
            return cand.strftime("%Y-%m-%d %H:%M")

        before = expected()
        snap = self.Audit._health_snapshot()
        after = expected()
        self.assertIn(snap["next_backup_at"], {before, after})

    def test_next_backup_at_none_when_param_garbage(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        self.Param.set_param("wms_gdrive.backup_time", "no-time")
        snap = self.Audit._health_snapshot()
        self.assertIsNone(snap["next_backup_at"])


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveFreshnessCron(GdriveHealthMixin, TransactionCase):
    """_cron_check_gdrive_freshness: stale upload -> one warning row + one
    manager notice per ~20h; quiet when fresh / disabled / never set up."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.Param = cls.env["ir.config_parameter"].sudo()

    def _warning_rows(self):
        return self.Audit.search(
            [
                ("audit_type", "=", "staleness_warning"),
                ("name", "=", "gdrive-freshness-check"),
            ]
        )

    def _run(self):
        with patch.object(audit_module, "notify_wms_managers") as notify:
            self.Audit._cron_check_gdrive_freshness()
        return notify

    def test_quiet_when_fresh(self):
        self._mk("backup_gdrive", True, 1)
        notify = self._run()
        self.assertFalse(self._warning_rows())
        notify.assert_not_called()

    def test_quiet_when_disabled(self):
        self.Param.set_param("wms_gdrive.enabled", "0")
        self._mk("backup_gdrive", True, 40)
        notify = self._run()
        self.assertFalse(self._warning_rows())
        notify.assert_not_called()

    def test_quiet_when_never_set_up(self):
        # No backup_gdrive rows + blank last_about: the stage is dark.
        self.Param.set_param("wms_gdrive.last_about", "")
        notify = self._run()
        self.assertFalse(self._warning_rows())
        notify.assert_not_called()

    def test_stale_writes_row_and_notifies_once_per_20h(self):
        self._mk("backup_gdrive", True, 30)
        notify = self._run()
        rows = self._warning_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("Google Drive", rows.message)
        self.assertIn("stale", rows.message)
        self.assertEqual(rows.host, "odoo-cron")
        self.assertEqual(notify.call_count, 1)
        # Second run inside the 20h window: dedupe swallows row AND notice.
        notify2 = self._run()
        self.assertEqual(len(self._warning_rows()), 1)
        notify2.assert_not_called()

    def test_dedupe_expires_after_20h(self):
        self._mk("backup_gdrive", True, 60)
        self._mk("staleness_warning", False, 21, name="gdrive-freshness-check")
        notify = self._run()
        self.assertEqual(len(self._warning_rows()), 2)
        self.assertEqual(notify.call_count, 1)

    def test_local_staleness_rows_do_not_suppress(self):
        # The local freshness cron's rows use name='freshness-check'; they
        # must never swallow the Drive warning (name-scoped dedupe).
        self._mk("backup_gdrive", True, 30)
        self._mk("staleness_warning", False, 1, name="freshness-check")
        self._run()
        self.assertEqual(len(self._warning_rows()), 1)

    def test_never_succeeded_counts_as_stale(self):
        self._mk("backup_gdrive", False, 2, message="quota exceeded")
        notify = self._run()
        rows = self._warning_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("no successful Google Drive upload", rows.message)
        self.assertEqual(notify.call_count, 1)

    def test_notify_failure_param_gates_notice_not_row(self):
        self.Param.set_param("wms_gdrive.notify_failure", "0")
        self._mk("backup_gdrive", True, 30)
        notify = self._run()
        self.assertEqual(len(self._warning_rows()), 1, "the audit row is always written")
        notify.assert_not_called()


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveEventsCron(GdriveHealthMixin, TransactionCase):
    """_cron_notify_gdrive_events: un-notified backup_gdrive /
    restore_gdrive rows -> manager notices, notified-flag dedupe,
    notify_success / notify_failure switches."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.Param = cls.env["ir.config_parameter"].sudo()

    def _run(self):
        with patch.object(audit_module, "notify_wms_managers") as notify:
            self.Audit._cron_notify_gdrive_events()
        return notify

    def test_failure_row_notifies_and_marks(self):
        row = self._mk("backup_gdrive", False, 1, message="Drive upload FAILED: quota")
        notify = self._run()
        self.assertTrue(row.notified)
        self.assertEqual(notify.call_count, 1)
        _env, body, subject = notify.call_args[0]
        self.assertIn("FAILED", subject)
        self.assertIn("Google Drive upload", str(body))
        self.assertIn("Local backup is intact", str(body))
        # Dedupe: the second run has nothing left to announce.
        notify2 = self._run()
        notify2.assert_not_called()

    def test_success_row_notifies_when_enabled(self):
        row = self._mk("backup_gdrive", True, 1, name="wms-20260612-163000.dump.gpg")
        notify = self._run()
        self.assertTrue(row.notified)
        self.assertEqual(notify.call_count, 1)
        _env, body, subject = notify.call_args[0]
        self.assertIn("OK", subject)
        self.assertIn("wms-20260612-163000.dump.gpg", str(body))

    def test_success_notice_suppressed_by_param_but_still_marked(self):
        self.Param.set_param("wms_gdrive.notify_success", "0")
        row = self._mk("backup_gdrive", True, 1)
        notify = self._run()
        notify.assert_not_called()
        self.assertTrue(
            row.notified,
            "suppressed rows are still marked handled so a later param "
            "flip cannot replay day-old events",
        )

    def test_failure_notice_suppressed_by_param_but_still_marked(self):
        self.Param.set_param("wms_gdrive.notify_failure", "0")
        row = self._mk("backup_gdrive", False, 1)
        notify = self._run()
        notify.assert_not_called()
        self.assertTrue(row.notified)

    def test_mixed_batch_honors_switches_per_row(self):
        self.Param.set_param("wms_gdrive.notify_success", "0")
        ok_row = self._mk("backup_gdrive", True, 2)
        fail_row = self._mk("backup_gdrive", False, 1, message="boom")
        notify = self._run()
        self.assertEqual(notify.call_count, 1, "only the failure is announced")
        self.assertIn("FAILED", notify.call_args[0][2])
        self.assertTrue(ok_row.notified)
        self.assertTrue(fail_row.notified)

    def test_restore_rows_use_restore_wording(self):
        self._mk("restore_gdrive", False, 1, message="VERIFY_FAILED")
        notify = self._run()
        self.assertEqual(notify.call_count, 1)
        _env, body, subject = notify.call_args[0]
        self.assertIn("Google Drive restore", subject)
        self.assertNotIn(
            "Local backup is intact",
            str(body),
            "the intact line is an upload-failure reassurance only",
        )

    def test_rows_older_than_24h_ignored(self):
        row = self._mk("backup_gdrive", False, 30)
        notify = self._run()
        notify.assert_not_called()
        self.assertFalse(row.notified)

    def test_other_audit_types_untouched(self):
        row = self._mk("backup_db", False, 1)
        notify = self._run()
        notify.assert_not_called()
        self.assertFalse(row.notified)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveHealthEndpoint(HttpCase):
    """/wms/health grows the spec section 5.1 keys automatically — the
    controller dumps _health_snapshot() as-is (spec section 12(a)7)."""

    def test_health_json_has_gate_key_when_dark(self):
        # Fresh test DB: the Drive stage is dark, only the gate key shows.
        resp = self.url_open("/wms/health")
        self.assertIn(resp.status_code, (200, 503))
        data = resp.json()
        self.assertIn("gdrive_enabled", data)
        self.assertFalse(data["gdrive_enabled"])
        self.assertNotIn("drive_connected", data)

    def test_health_json_full_drive_block_when_live(self):
        self.env["wms.backup.audit"].record_event(
            {
                "name": "wms-20260612-163000.dump.gpg",
                "audit_type": "backup_gdrive",
                "success": True,
            }
        )
        resp = self.url_open("/wms/health")
        self.assertIn(resp.status_code, (200, 503))
        data = resp.json()
        self.assertTrue(data["gdrive_enabled"])
        for key in (
            "drive_connected",
            "last_upload_age_hours",
            "drive_storage_used_mb",
            "drive_storage_limit_mb",
            "next_backup_at",
        ):
            self.assertIn(key, data, "/wms/health must expose %s" % key)
        self.assertTrue(data["drive_connected"])


# =========================================================================
# v18 offline-first Google Drive backup queue (spec v18-offline-spec.md).
#
# The catalog row is now AUTHORITATIVE for the offline queue: the 5 new
# plain-stored columns (queue_state / retry_count / last_error /
# error_class / next_retry_at) are psql-written by Set-GDriveQueueFailure /
# the Stage 5a sweep / Send-GDriveBackupSet (see the model docstring's
# COLUMN CONTRACT). Odoo only READS them. These suites seed rows (the only
# Odoo-side test door — spec section 8) and assert the model defaults, the
# plain-stored drift guard, the seeded params, the live/dark health-snapshot
# queue keys (DEGRADED-only, NEVER CRITICAL), the DR-page wizard fields /
# onchange / subprocess seams / manager-only & storekeeper gates, and the
# hourly reconnect cron.
# =========================================================================

# The 5 v18 queue columns appended to Write-GDriveCatalogRow's $allowed
# whitelist (scripts/gdrive-lib.ps1) IN THE SAME COMMIT as the model fields.
# psql writes them via the same plain-stored path as CATALOG_COLUMNS, so the
# same rename/add-in-lockstep contract applies (spec sections 1.1 / 1.2).
QUEUE_COLUMNS = [
    "queue_state",
    "retry_count",
    "last_error",
    "error_class",
    "next_retry_at",
]

# The 5 offline-queue ir.config_parameter keys seeded by data/gdrive_params.xml
# under noupdate=1 (spec section 2). parent_folder_id seeds as '' and is
# probed separately (get_param coalesces '' to its default).
OFFLINE_PARAM_DEFAULTS = {
    "wms_gdrive.offline_retry_max": "8",
    "wms_gdrive.offline_retry_window_days": "14",
    "wms_gdrive.offline_retry_max_per_run": "5",
    "wms_gdrive.offline_backoff_base_min": "15",
}


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveQueueColumns(TransactionCase):
    """The 5 v18 offline-queue catalog columns: record_set door accepts
    them, defaults agree with the script's first-write expectations, and
    the plain-stored drift guard holds (psql bypasses the ORM, so a
    compute/related/onchange on any of them would silently diverge)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Catalog = cls.env["wms.gdrive.backup"]

    def test_queue_columns_exist(self):
        for col in QUEUE_COLUMNS:
            self.assertIn(
                col,
                self.Catalog._fields,
                "queue column %r missing — Set-GDriveQueueFailure / the "
                "Stage 5a sweep write it via psql" % col,
            )

    def test_queue_columns_are_plain_stored(self):
        # Same contract as CATALOG_COLUMNS: psql writes bypass the ORM, so a
        # compute / related / onchange would silently diverge from the script.
        for col in QUEUE_COLUMNS:
            field = self.Catalog._fields[col]
            self.assertTrue(field.store, "queue column %r must be stored" % col)
            self.assertFalse(field.compute, "queue column %r must not be computed" % col)
            self.assertFalse(field.related, "queue column %r must not be related" % col)
            self.assertFalse(field.inverse, "queue column %r must not have an inverse" % col)

    def test_queue_state_defaults_to_created(self):
        # The Stage 5b "created" row is written before the first upload
        # attempt; the ORM default must match so a seeded row agrees.
        rec = self.Catalog.record_set({"name": "wms-20260613-163000.dump.gpg"})
        self.assertEqual(rec.queue_state, "created")

    def test_retry_count_defaults_to_zero(self):
        rec = self.Catalog.record_set({"name": "wms-20260613-163000.dump.gpg"})
        self.assertEqual(rec.retry_count, 0)
        # last_error / error_class / next_retry_at are unset on a fresh row.
        self.assertFalse(rec.last_error)
        self.assertFalse(rec.error_class)
        self.assertFalse(rec.next_retry_at)

    def test_record_set_accepts_queue_failure_vals(self):
        # Exactly the shape Set-GDriveQueueFailure UPSERTs on an offline
        # failure: waiting / retry_count++ / error_class / next_retry_at.
        next_at = fields.Datetime.now() + timedelta(minutes=15)
        rec = self.Catalog.record_set(
            {
                "name": "wms-20260613-170000.dump.gpg",
                "queue_state": "waiting",
                "retry_count": 1,
                "error_class": "offline",
                "last_error": "Drive API GET about failed (HTTP 0, offline)",
                "next_retry_at": next_at,
            }
        )
        self.assertEqual(rec.queue_state, "waiting")
        self.assertEqual(rec.retry_count, 1)
        self.assertEqual(rec.error_class, "offline")
        self.assertIn("offline", rec.last_error)
        self.assertEqual(rec.next_retry_at, next_at)

    def test_record_set_accepts_uploaded_terminal_state(self):
        # Send-GDriveBackupSet's success UPSERT sets queue_state='uploaded'
        # in the SAME row write as uploaded=true (they never diverge).
        rec = self.Catalog.record_set(
            {
                "name": "wms-20260613-170100.dump.gpg",
                "queue_state": "uploaded",
                "uploaded": True,
                "retry_count": 3,
            }
        )
        self.assertEqual(rec.queue_state, "uploaded")
        self.assertTrue(rec.uploaded)
        self.assertEqual(rec.retry_count, 3, "retry_count is preserved as the attempt audit trail")

    def test_error_class_is_free_char_not_selection(self):
        # error_class is a Char, NOT a Selection: an unexpected class string
        # from a future PowerShell change must never raise on the psql path
        # (Selections validate on ORM write; a Char is contract-safe).
        field = self.Catalog._fields["error_class"]
        self.assertEqual(field.type, "char")
        rec = self.Catalog.record_set(
            {"name": "wms-20260613-170200.dump.gpg", "error_class": "some_future_class"}
        )
        self.assertEqual(rec.error_class, "some_future_class")

    def test_queue_state_selection_keys(self):
        keys = dict(self.Catalog._fields["queue_state"].selection)
        for state in ("created", "waiting", "uploading", "uploaded", "failed", "abandoned"):
            self.assertIn(state, keys, "queue_state must offer the %r lifecycle value" % state)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveOfflineParams(TransactionCase):
    """The 5 offline-queue ir.config_parameter keys: seeded defaults,
    write/read round-trip (the shared Odoo<->PowerShell contract), and the
    blank-probe for parent_folder_id (seeded '' so the key exists)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Param = cls.env["ir.config_parameter"].sudo()

    def test_offline_params_seeded_with_defaults(self):
        for key, default in OFFLINE_PARAM_DEFAULTS.items():
            self.assertEqual(
                self.Param.get_param(key),
                default,
                "%s must be seeded to %r by data/gdrive_params.xml" % (key, default),
            )

    def test_parent_folder_id_seeded_blank(self):
        # Seeded '' so the key exists for the script/wizard handshake;
        # get_param('') falls back to its default, so probe the row.
        self.assertTrue(
            self.Param.search_count([("key", "=", "wms_gdrive.parent_folder_id")]),
            "wms_gdrive.parent_folder_id must be seeded (blank) by data/gdrive_params.xml",
        )

    def test_offline_params_round_trip(self):
        # The scripts read these via Get-WmsConfigParam (psql); a write here
        # must survive a read unchanged (they are the remote config).
        for key in OFFLINE_PARAM_DEFAULTS:
            self.Param.set_param(key, "11")
            self.assertEqual(self.Param.get_param(key), "11")
        self.Param.set_param("wms_gdrive.parent_folder_id", "1AbC_def-GHIjkl")
        self.assertEqual(self.Param.get_param("wms_gdrive.parent_folder_id"), "1AbC_def-GHIjkl")


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveQueueHealthSnapshot(GdriveHealthMixin, TransactionCase):
    """_health_snapshot() offline-queue keys (spec section 5.1): present
    when the Drive tier is LIVE, absent when dark, and a backed-up /
    abandoned queue escalates to DEGRADED — NEVER CRITICAL."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Catalog = cls.env["wms.gdrive.backup"]

    def _seed_set(self, name, queue_state, retry_count=0, **extra):
        vals = {"name": name, "queue_state": queue_state, "retry_count": retry_count}
        vals.update(extra)
        return self.Catalog.record_set(vals)

    # The 7 offline-queue keys _gdrive_snapshot_fields adds when live.
    _QUEUE_KEYS = (
        "queued_count",
        "queue_waiting",
        "queue_abandoned_count",
        "queue_oldest_age_hours",
        "queue_max_retry",
        "last_failure_time",
        "last_failure_message",
    )

    def test_queue_keys_present_when_live(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)  # makes the Drive tier live
        self._seed_set("wms-a.dump.gpg", "waiting", retry_count=2)
        self._seed_set("wms-b.dump.gpg", "created")
        self._seed_set("wms-c.dump.gpg", "uploaded", uploaded=True)
        snap = self.Audit._health_snapshot()
        for key in self._QUEUE_KEYS:
            self.assertIn(key, snap, "%s must be exposed when the Drive tier is live" % key)
        # created + waiting are pending; uploaded is terminal (excluded).
        self.assertEqual(snap["queued_count"], 2)
        self.assertEqual(snap["queue_waiting"], 1)
        self.assertEqual(snap["queue_abandoned_count"], 0)
        self.assertEqual(snap["queue_max_retry"], 2)

    def test_queue_keys_absent_when_disabled(self):
        # Kill-switch dark: only the gate key, even with queue rows seeded.
        self._seed_local_healthy()
        self.Param.set_param("wms_gdrive.enabled", "0")
        self._mk("backup_gdrive", True, 1)
        self._seed_set("wms-a.dump.gpg", "waiting")
        snap = self.Audit._health_snapshot()
        self.assertFalse(snap["gdrive_enabled"])
        for key in self._QUEUE_KEYS:
            self.assertNotIn(key, snap, "%s must be absent when Drive is disabled" % key)
        self.assertEqual(snap["status"], "HEALTHY", "a kill-switched Drive stage cannot degrade")

    def test_queue_keys_absent_when_dark(self):
        # enabled but never set up (no backup_gdrive rows, blank about):
        # the whole Drive block stays dark even though queue rows exist.
        self._seed_local_healthy()
        self.Param.set_param("wms_gdrive.last_about", "")
        self._seed_set("wms-a.dump.gpg", "waiting")
        snap = self.Audit._health_snapshot()
        self.assertFalse(snap["gdrive_enabled"])
        for key in self._QUEUE_KEYS:
            self.assertNotIn(key, snap)
        self.assertEqual(snap["status"], "HEALTHY")

    def test_abandoned_set_is_degraded_never_critical(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        self._seed_set("wms-doomed.dump.gpg", "abandoned", retry_count=8)
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["queue_abandoned_count"], 1)
        self.assertTrue(
            any("abandoned" in w for w in snap["warnings"]),
            "an abandoned set must raise a manager-facing warning",
        )
        self.assertEqual(
            snap["status"],
            "DEGRADED",
            "an abandoned Drive set is DEGRADED — CRITICAL stays reserved for local",
        )

    def test_backed_up_queue_warns_degraded(self):
        # A pending set older than GDRIVE_STALE_HOURS -> backed-up warning.
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        stale = self.Catalog.record_set(
            {"name": "wms-stuck.dump.gpg", "queue_state": "waiting", "retry_count": 1}
        )
        old = fields.Datetime.now() - timedelta(hours=audit_module.GDRIVE_STALE_HOURS + 5)
        # create_date is the "oldest pending age" source; force it back.
        self.env.cr.execute(
            "UPDATE wms_gdrive_backup SET create_date = %s WHERE id = %s",
            (old, stale.id),
        )
        stale.invalidate_recordset(["create_date"])
        snap = self.Audit._health_snapshot()
        self.assertTrue(
            any("queue backed up" in w for w in snap["warnings"]),
            "a long-pending set must raise the backed-up warning",
        )
        self.assertEqual(snap["status"], "DEGRADED")
        self.assertIsNotNone(snap["queue_oldest_age_hours"])
        self.assertGreater(snap["queue_oldest_age_hours"], audit_module.GDRIVE_STALE_HOURS)

    def test_last_failure_fields_from_newest_failed_audit(self):
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 30)
        self._mk(
            "backup_gdrive",
            False,
            1,
            message="Drive upload FAILED: storageQuotaExceeded (quota)",
        )
        snap = self.Audit._health_snapshot()
        self.assertTrue(snap["last_failure_time"])
        self.assertIn("storageQuotaExceeded", snap["last_failure_message"])

    def test_all_queue_problems_at_once_only_degraded(self):
        # Abandoned + backed-up + a fresh failure together never reach
        # CRITICAL: the local pipeline is healthy, so Drive stays DEGRADED.
        self._seed_local_healthy()
        self._mk("backup_gdrive", True, 1)
        self._mk("backup_gdrive", False, 1, message="boom")
        self._seed_set("wms-dead.dump.gpg", "abandoned", retry_count=8)
        stuck = self.Catalog.record_set(
            {"name": "wms-stuck.dump.gpg", "queue_state": "failed", "retry_count": 4}
        )
        old = fields.Datetime.now() - timedelta(hours=audit_module.GDRIVE_STALE_HOURS + 10)
        self.env.cr.execute(
            "UPDATE wms_gdrive_backup SET create_date = %s WHERE id = %s",
            (old, stuck.id),
        )
        stuck.invalidate_recordset(["create_date"])
        snap = self.Audit._health_snapshot()
        self.assertEqual(snap["status"], "DEGRADED")
        self.assertNotEqual(snap["status"], "CRITICAL")
        self.assertEqual(snap["queue_abandoned_count"], 1)
        self.assertEqual(snap["queue_max_retry"], 4)


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveDrPageQueue(GdriveUsersMixin, TransactionCase):
    """The Backup & Disaster Recovery page (extended wms.gdrive.settings):
    the 5 offline-tuning params round-trip, folder-URL id extraction, the
    validate-folder / disconnect subprocess seams, and the manager-only +
    storekeeper-exclusion gates (spec sections 6 / 7 / 9)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Wizard = cls.env["wms.gdrive.settings"]

    # --- offline-tuning param round-trip ----------------------------------
    def test_default_get_loads_offline_params(self):
        self.Param.set_param("wms_gdrive.offline_retry_max", "12")
        self.Param.set_param("wms_gdrive.offline_retry_window_days", "21")
        self.Param.set_param("wms_gdrive.offline_retry_max_per_run", "7")
        self.Param.set_param("wms_gdrive.offline_backoff_base_min", "20")
        self.Param.set_param("wms_gdrive.parent_folder_id", "1AbC_def-GHIjkl")
        wiz = self.Wizard.create({})
        self.assertEqual(wiz.offline_retry_max, 12)
        self.assertEqual(wiz.offline_retry_window_days, 21)
        self.assertEqual(wiz.offline_retry_max_per_run, 7)
        self.assertEqual(wiz.offline_backoff_base_min, 20)
        self.assertEqual(wiz.parent_folder_id, "1AbC_def-GHIjkl")

    def test_save_round_trips_offline_params(self):
        wiz = self.Wizard.create({})
        wiz.write(
            {
                "offline_retry_max": 9,
                "offline_retry_window_days": 15,
                "offline_retry_max_per_run": 6,
                "offline_backoff_base_min": 30,
                "parent_folder_id": "0BxY-zzz_123456",
            }
        )
        wiz.action_save()
        self.assertEqual(self.Param.get_param("wms_gdrive.offline_retry_max"), "9")
        self.assertEqual(self.Param.get_param("wms_gdrive.offline_retry_window_days"), "15")
        self.assertEqual(self.Param.get_param("wms_gdrive.offline_retry_max_per_run"), "6")
        self.assertEqual(self.Param.get_param("wms_gdrive.offline_backoff_base_min"), "30")
        self.assertEqual(self.Param.get_param("wms_gdrive.parent_folder_id"), "0BxY-zzz_123456")

    def test_save_validates_offline_ints_positive(self):
        wiz = self.Wizard.create({})
        wiz.offline_retry_max = 0
        with self.assertRaises(UserError):
            wiz.action_save()

    def test_save_validates_parent_folder_id_charset(self):
        wiz = self.Wizard.create({})
        wiz.parent_folder_id = "too short!"  # fails ^[A-Za-z0-9_-]{10,}$
        with self.assertRaises(UserError):
            wiz.action_save()

    # --- folder-URL -> bare-id onchange (the raw URL never reaches PS) ----
    def test_onchange_folder_url_folders_form(self):
        wiz = self.Wizard.new({})
        wiz.folder_url = "https://drive.google.com/drive/folders/1A2b3C4d5E6f7G8h9I0j"
        wiz._onchange_folder_url()
        self.assertEqual(wiz.parent_folder_id, "1A2b3C4d5E6f7G8h9I0j")

    def test_onchange_folder_url_d_form(self):
        wiz = self.Wizard.new({})
        wiz.folder_url = "https://drive.google.com/file/d/1A2b3C4d5E6f7G8h9I0j/view"
        wiz._onchange_folder_url()
        self.assertEqual(wiz.parent_folder_id, "1A2b3C4d5E6f7G8h9I0j")

    def test_onchange_folder_url_id_query_form(self):
        wiz = self.Wizard.new({})
        wiz.folder_url = "https://drive.google.com/open?id=1A2b3C4d5E6f7G8h9I0j"
        wiz._onchange_folder_url()
        self.assertEqual(wiz.parent_folder_id, "1A2b3C4d5E6f7G8h9I0j")

    def test_onchange_folder_url_no_match_leaves_id(self):
        wiz = self.Wizard.new({"parent_folder_id": "0BxY-zzz_123456"})
        wiz.folder_url = "https://example.com/not-a-drive-link"
        wiz._onchange_folder_url()
        self.assertEqual(wiz.parent_folder_id, "0BxY-zzz_123456")

    # --- validate-folder / disconnect subprocess seams --------------------
    def _stub_gdrive_test(self, stdout):
        """Same stub idiom as TestGdriveSettingsWizard: resolve the script
        path to a file that exists, and feed one JSON stdout line."""
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")
        return (
            patch.object(
                settings_wizard.WmsGdriveSettings,
                "_gdrive_test_script_path",
                return_value=os.path.abspath(__file__),
            ),
            patch.object(settings_wizard.subprocess, "run", return_value=fake),
        )

    def test_validate_folder_renders_success(self):
        wiz = self.Wizard.create({"parent_folder_id": "1A2b3C4d5E6f7G8h9I0j"})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": true, "name": "Inventory_Backups", '
            b'"owner": "office.dakshinvrindavan@gmail.com", '
            b'"accessible": true, "writable": true}'
        )
        with path_patch, run_patch:
            wiz.action_validate_folder()
        self.assertIn("Folder is valid", wiz.folder_validate_html)
        self.assertIn("Inventory_Backups", wiz.folder_validate_html)
        self.assertIn("office.dakshinvrindavan@gmail.com", wiz.folder_validate_html)

    def test_validate_folder_not_writable_warns(self):
        wiz = self.Wizard.create({"parent_folder_id": "1A2b3C4d5E6f7G8h9I0j"})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": true, "name": "Shared", "owner": "someone@else.com", '
            b'"accessible": true, "writable": false}'
        )
        with path_patch, run_patch:
            wiz.action_validate_folder()
        self.assertIn("cannot add files", wiz.folder_validate_html)

    def test_validate_folder_auth_expired_renders_reconnect(self):
        wiz = self.Wizard.create({"parent_folder_id": "1A2b3C4d5E6f7G8h9I0j"})
        path_patch, run_patch = self._stub_gdrive_test(
            b'{"ok": false, "error": "GDRIVE_AUTH_EXPIRED: token refresh rejected", '
            b'"auth_expired": true}'
        )
        with path_patch, run_patch:
            wiz.action_validate_folder()
        self.assertIn("Folder check failed", wiz.folder_validate_html)
        self.assertIn("setup-gdrive-auth.ps1", wiz.folder_validate_html)

    def test_validate_folder_no_id_is_soft_note(self):
        # No folder id set: the page renders a "default folder" note and
        # never shells out (no subprocess to stub).
        wiz = self.Wizard.create({"parent_folder_id": ""})
        wiz.action_validate_folder()
        self.assertIn("default folder", wiz.folder_validate_html)

    def test_validate_folder_script_missing_is_graceful(self):
        # FileNotFoundError out of subprocess.run -> soft "check failed",
        # never a raw traceback (the _run_gdrive_test OSError guard).
        wiz = self.Wizard.create({"parent_folder_id": "1A2b3C4d5E6f7G8h9I0j"})
        with (
            patch.object(
                settings_wizard.WmsGdriveSettings,
                "_gdrive_test_script_path",
                return_value=os.path.abspath(__file__),
            ),
            patch.object(
                settings_wizard.subprocess, "run", side_effect=FileNotFoundError("powershell.exe")
            ),
        ):
            wiz.action_validate_folder()  # must NOT raise
        self.assertIn("Folder check failed", wiz.folder_validate_html)
        self.assertNotIn("FileNotFoundError", wiz.folder_validate_html)

    def test_disconnect_revoke_success(self):
        # test_skip_schtasks makes _run_setup_auth report success without a
        # subprocess; the page confirms the revoke + the local-safe message.
        wiz = self.Wizard.with_context(test_skip_schtasks=True).create({})
        wiz.action_disconnect()
        self.assertIn("Disconnected", wiz.result_html)
        self.assertIn("Local", wiz.result_html)

    def test_disconnect_file_not_found_is_graceful(self):
        # No skip seam: subprocess.run raises like a host without
        # powershell.exe -> graceful fallback, no raw exception in the HTML.
        # scripts/setup-gdrive-auth.ps1 exists in the repo, so _run_setup_auth
        # passes its own existence guard and reaches the patched subprocess.run
        # (no os.path.isfile patch — that would perturb Odoo internals).
        wiz = self.Wizard.create({})
        with patch.object(
            settings_wizard.subprocess, "run", side_effect=FileNotFoundError("powershell.exe")
        ):
            wiz.action_disconnect()  # must NOT raise
        self.assertIn("Could not revoke", wiz.result_html)
        self.assertNotIn("FileNotFoundError", wiz.result_html)

    # --- manager-only + storekeeper exclusion (three-gate, spec 6.1/9) ----
    def test_check_manager_raises_for_non_manager(self):
        # Defense-in-depth gate 3: _check_manager() short-circuits under su,
        # so create the record in the (su) test env, then rebind the action
        # call to a plain keeper — with_user() drops su, the has_group gate
        # fires, and the action raises AccessError before doing any work.
        keeper = self._user("wms_location.group_wms_user", "gd_dr_keeper")
        wiz = self.Wizard.create({})
        with self.assertRaises(AccessError):
            wiz.with_user(keeper).action_retry_now()

    def test_manager_passes_check_manager(self):
        mgr = self._user("wms_location.group_wms_manager", "gd_dr_mgr")
        wiz = self.Wizard.with_user(mgr).with_context(test_skip_schtasks=True).create({})
        # Reaches the action body (no AccessError) and renders a result.
        wiz.action_retry_now()
        self.assertTrue(wiz.result_html)

    def test_storekeeper_cannot_read_settings_model(self):
        # Structural exclusion: the model ACL is manager-only, so a plain
        # keeper (and the Backup Now capability keeper) cannot even read it.
        keeper = self._user("wms_location.group_wms_user", "gd_dr_keeper2")
        cap = self._user("wms_reports.group_wms_backup_now", "gd_dr_cap")
        mgr = self._user("wms_location.group_wms_manager", "gd_dr_mgr2")
        self.assertFalse(self._can(keeper, "wms.gdrive.settings", "read"))
        self.assertFalse(self._can(cap, "wms.gdrive.settings", "read"))
        self.assertTrue(self._can(mgr, "wms.gdrive.settings", "read"))


@tagged("post_install", "-at_install", "wms", "wms_gdrive")
class TestGdriveReconnectCron(GdriveHealthMixin, TransactionCase):
    """_cron_retry_gdrive_uploads (hourly :45): when the Drive tier is live
    AND offline-queued sets exist, /Run the 'WMS Pending Upload Sweep'
    SYSTEM task; quiet when the queue is empty or the stage is
    kill-switched. The cron only TRIGGERS — the existing :25 event notifier
    delivers the Discuss notice (spec section 5.2)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Audit = cls.env["wms.backup.audit"]
        cls.Param = cls.env["ir.config_parameter"].sudo()
        cls.Catalog = cls.env["wms.gdrive.backup"]

    def _seed_set(self, name, queue_state, **extra):
        vals = {"name": name, "queue_state": queue_state}
        vals.update(extra)
        return self.Catalog.record_set(vals)

    def test_pending_set_triggers_sweep_task(self):
        # test_skip_schtasks asserts the cron reaches the /Run seam without
        # ever spawning a subprocess (the seam returns success).
        self._seed_set("wms-waiting.dump.gpg", "waiting")
        with patch.object(type(self.Audit), "_run_pending_sweep_task", return_value=(0, "")) as run:
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        run.assert_called_once()

    def test_no_subprocess_under_test_skip(self):
        # Belt-and-braces: even reaching the real seam spawns nothing under
        # the skip context, so subprocess.run is never called.
        self._seed_set("wms-waiting.dump.gpg", "waiting")
        with patch.object(audit_module.subprocess, "run") as run:
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        run.assert_not_called()

    def test_noop_when_queue_empty(self):
        # Live tier (a successful upload row) but no pending sets -> no /Run.
        self._mk("backup_gdrive", True, 1)
        with patch.object(type(self.Audit), "_run_pending_sweep_task") as run:
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        run.assert_not_called()

    def test_noop_when_only_terminal_sets(self):
        # uploaded / abandoned are terminal — they are NOT pending, so the
        # reconnect loop has nothing to retry.
        self._seed_set("wms-done.dump.gpg", "uploaded", uploaded=True)
        self._seed_set("wms-dead.dump.gpg", "abandoned", retry_count=8)
        with patch.object(type(self.Audit), "_run_pending_sweep_task") as run:
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        run.assert_not_called()

    def test_noop_when_stage_disabled(self):
        # Kill-switch beats a non-empty queue: no /Run when disabled.
        self.Param.set_param("wms_gdrive.enabled", "0")
        self._seed_set("wms-waiting.dump.gpg", "waiting")
        with patch.object(type(self.Audit), "_run_pending_sweep_task") as run:
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        run.assert_not_called()

    def test_cron_does_not_notify_directly(self):
        # The reconnect cron only triggers the sweep; it must NOT post a
        # Discuss notice itself (the :25 event notifier owns that — no new
        # notification path).
        self._seed_set("wms-waiting.dump.gpg", "waiting")
        with (
            patch.object(audit_module, "notify_wms_managers") as notify,
            patch.object(type(self.Audit), "_run_pending_sweep_task", return_value=(0, "")),
        ):
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()
        notify.assert_not_called()

    def test_graceful_when_task_absent(self):
        # A missing task surfaces as rc != 0; the cron logs and no-ops
        # (never raises — the daily -StartWhenAvailable catch-up is the
        # documented fallback).
        self._seed_set("wms-waiting.dump.gpg", "waiting")
        with patch.object(
            type(self.Audit),
            "_run_pending_sweep_task",
            return_value=(1, "ERROR: task not found"),
        ):
            # Must not raise.
            self.Audit.with_context(test_skip_schtasks=True)._cron_retry_gdrive_uploads()

    def test_run_pending_sweep_task_skip_seam(self):
        # The seam itself returns (0, '') under the skip context with no
        # subprocess — the deterministic test door for the whole feature.
        with patch.object(audit_module.subprocess, "run") as run:
            rc, detail = self.Audit.with_context(test_skip_schtasks=True)._run_pending_sweep_task()
        self.assertEqual(rc, 0)
        self.assertEqual(detail, "")
        run.assert_not_called()

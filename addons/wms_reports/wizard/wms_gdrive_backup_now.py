# -*- coding: utf-8 -*-
"""Backup Now wizard (P6) — plain-language, zero-technical-knowledge UI.

The wizard NEVER runs pg_dump in the HTTP thread and never talks to
Google Drive itself: it fires the trigger-less "WMS Manual Backup"
Scheduled Task via ``schtasks /Run`` (design D5), so the manual backup
runs in the exact same SYSTEM context as the nightly one, survives an
Odoo restart, and double-clicks are harmless (the task is registered
with MultipleInstances IgnoreNew). Completion is then read back by
polling ``wms.backup.audit`` rows — the only completion signal the
out-of-process pipeline already emits — so this is deterministic and
zero-mock testable (seed audit rows, call refresh).

Requester attribution handshake (D5): before /Run the wizard writes
``wms_gdrive.last_manual_requester = "<login>|<iso-ts>"``;
backup-native.ps1 -Source manual reads it via psql and stamps the login
as the set's creator when the timestamp is less than 10 minutes old.

Security: the menu, the model ACL AND a defense-in-depth group re-check
inside every action gate this on wms_reports.group_wms_backup_now (or
manager). The wizard can only ever /Run the fixed task name below —
no user input reaches the command line — and it exposes sanitized
plain-language strings only: keepers get no restore power and never
see a raw exception.
"""
import logging
import subprocess
from datetime import datetime, timezone

from markupsafe import Markup
from odoo import fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

# Fixed Scheduled Task name registered by scripts/install-backup-tasks.ps1.
# Never built from user input — the injection surface is zero.
MANUAL_TASK_NAME = "WMS Manual Backup"


class WmsGdriveBackupNow(models.TransientModel):
    _name = "wms.gdrive.backup.now"
    _description = "Run a WMS backup now (local + Google Drive)"

    state = fields.Selection(
        [
            ("ready", "Ready"),
            ("running", "Running"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="ready",
        readonly=True,
    )
    requested_at = fields.Datetime(
        readonly=True,
        help="When Back Up Now was clicked. The Refresh poll only looks at "
        "wms.backup.audit rows recorded at or after this moment.",
    )
    result_html = fields.Html(readonly=True, sanitize=False)

    # --- Guards / seams ----------------------------------------------------
    def _check_can_run(self):
        """Defense-in-depth group re-check (the menu + ACL already gate)."""
        if self.env.su:
            return
        user = self.env.user
        if not (
            user.has_group("wms_reports.group_wms_backup_now")
            or user.has_group("wms_location.group_wms_manager")
        ):
            raise AccessError("You are not allowed to run backups. Ask your administrator.")

    def _run_schtasks(self):
        """Fire the on-demand manual-backup task. Returns (rc, detail).

        Isolated so tests can short-circuit it: with context key
        ``test_skip_schtasks`` the subprocess is never spawned and the
        call reports success. Argument-array invocation only (no shell
        string interpolation) with the fixed task name constant.
        """
        if self.env.context.get("test_skip_schtasks"):
            return 0, ""
        try:
            proc = subprocess.run(
                ["schtasks.exe", "/Run", "/TN", MANUAL_TASK_NAME],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, str(exc)
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        return proc.returncode, detail

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Back Up Now",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # --- Actions -----------------------------------------------------------
    def action_backup_now(self):
        self.ensure_one()
        self._check_can_run()
        param = self.env["ir.config_parameter"].sudo()

        if param.get_param("wms_gdrive.manual_enabled", "1") == "0":
            self.write(
                {
                    "state": "failed",
                    "result_html": Markup(
                        "<p><b>Backup Now is turned off.</b></p>"
                        "<p>Your administrator has disabled manual backups "
                        "(setting <code>wms_gdrive.manual_enabled</code>). "
                        "The daily automatic backup still runs as scheduled.</p>"
                    ),
                }
            )
            return self._reopen()

        # D5 requester-attribution handshake, written BEFORE /Run so the
        # script (running as SYSTEM) can stamp the creator.
        stamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        param.set_param(
            "wms_gdrive.last_manual_requester", "%s|%s" % (self.env.user.login, stamp_utc)
        )

        # Record the poll watermark before firing the task: a completion row
        # can never land in the gap between /Run and our write.
        self.write({"requested_at": fields.Datetime.now()})

        rc, detail = self._run_schtasks()
        if rc != 0:
            _logger.warning(
                "Backup Now: schtasks /Run %r failed rc=%s: %s", MANUAL_TASK_NAME, rc, detail
            )
            self.write(
                {
                    "state": "failed",
                    "result_html": Markup(
                        "<p><b>Could not start the backup.</b></p>"
                        "<p>The '%s' scheduled task is not installed on this "
                        "server (or could not be started). Ask your "
                        "administrator to run "
                        "<code>scripts\\install-backup-tasks.ps1</code> once, "
                        "then try again.</p>"
                        "<p>Your daily automatic backup is not affected.</p>"
                    )
                    % MANUAL_TASK_NAME,
                }
            )
            return self._reopen()

        self.write(
            {
                "state": "running",
                "result_html": Markup(
                    "<p><b>Backup started.</b> The server is making a safe "
                    "copy of all WMS data and will then send it to Google "
                    "Drive.</p>"
                    "<p>This usually takes a few minutes. Click "
                    "<b>Refresh</b> to check progress — you can also close "
                    "this window and keep working.</p>"
                ),
            }
        )
        return self._reopen()

    def action_refresh(self):
        """Poll wms.backup.audit (sudo) for rows since requested_at (D5).

        Plain-language outcomes only — raw script errors stay in the
        audit table for managers; keepers see a friendly summary.
        """
        self.ensure_one()
        self._check_can_run()
        if not self.requested_at:
            return self._reopen()

        rows = (
            self.env["wms.backup.audit"]
            .sudo()
            .search([("event_time", ">=", self.requested_at)], order="event_time asc")
        )
        db_ok = rows.filtered(lambda r: r.audit_type == "backup_db" and r.success)[-1:]
        local_fail = rows.filtered(
            lambda r: r.audit_type in ("backup_db", "backup_filestore") and not r.success
        )
        drive_ok = rows.filtered(lambda r: r.audit_type == "backup_gdrive" and r.success)[-1:]
        drive_fail = rows.filtered(lambda r: r.audit_type == "backup_gdrive" and not r.success)

        if local_fail and not db_ok:
            self.write(
                {
                    "state": "failed",
                    "result_html": Markup(
                        "<p><b>The backup did not complete.</b></p>"
                        "<p>Nothing was lost — all previous backups are "
                        "untouched. Ask your administrator to open "
                        "<i>WMS &rsaquo; Reports &rsaquo; Backup &amp; DR "
                        "Audit</i> for the technical detail.</p>"
                    ),
                }
            )
            return self._reopen()

        if not db_ok:
            # No completion row yet: the pipeline is still running.
            self.write(
                {
                    "state": "running",
                    "result_html": Markup(
                        "<p><b>Still working…</b></p>"
                        "<p>The backup is running in the background — this "
                        "takes a few minutes. Click <b>Refresh</b> again in "
                        "a moment.</p>"
                    ),
                }
            )
            return self._reopen()

        html = Markup("<p><b>Backup complete.</b></p>")
        html += Markup("<p>%s (%.1f MB) backed up at %s.</p>") % (
            db_ok.name,
            db_ok.size_mb or 0.0,
            self._fmt_time(db_ok.event_time),
        )
        if drive_ok:
            # The Drive display name lives in the catalog row the script
            # UPSERTed (D8: audit rows keep the LOCAL filename).
            catalog = (
                self.env["wms.gdrive.backup"].sudo().search([("name", "=", db_ok.name)], limit=1)
            )
            html += Markup("<p>Uploaded to Google Drive at %s as %s.</p>") % (
                self._fmt_time(drive_ok.event_time),
                catalog.drive_name or drive_ok.name,
            )
        elif drive_fail:
            html += Markup(
                "<p>Drive upload pending — it will be retried automatically "
                "on the next run. Your local backup is safe.</p>"
            )
        self.write({"state": "done", "result_html": html})
        return self._reopen()

    def _fmt_time(self, dt):
        """HH:MM in the user's timezone (audit rows are stored UTC)."""
        return fields.Datetime.context_timestamp(self, dt).strftime("%H:%M")

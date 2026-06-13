# -*- coding: utf-8 -*-
"""Google Drive backup settings wizard (P12).

No res.config.settings exists anywhere in this project; the house
pattern is namespaced raw ir.config_parameter values read with
``.sudo().get_param()`` (D9). This TransientModel is the friendly face
over the ``wms_gdrive.*`` namespace: ``default_get`` loads the params,
``action_save`` writes them back. The parameters double as the
PowerShell pipeline's remote config (Get-WmsConfigParam in
scripts/gdrive-lib.ps1 reads them via psql with failure-safe defaults,
so a down DB never blocks a local backup).

Test Connection / Test Upload shell out to scripts/gdrive-test.ps1 —
the SAME PowerShell stack the nightly pipeline uses (one credential
path, one retry policy, D2/D5) — and parse its single JSON stdout
line. Apply Schedule is a best-effort ``schtasks /Change`` on the
daily task (Odoo-WMS runs as LocalSystem, so this works); on failure
it shows the install-backup-tasks.ps1 fallback instead of throwing.

Security: manager-only (menu + ACL + defense-in-depth group re-check
in every action). Subprocess calls use argument arrays with fixed
task/script names and a mode string from a fixed set — wizard inputs
never reach the command line (the schedule time is regex-validated
to HH:MM before use).
"""
import json
import logging
import os
import re
import subprocess

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# Fixed Scheduled Task name registered by scripts/install-backup-tasks.ps1.
DAILY_TASK_NAME = "WMS Daily Backup"

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TRUE = ("1", "true", "True", "yes", "on")

# (field name, ir.config_parameter key, type, seeded default) — mirrors
# spec section 2.3 / data/gdrive_params.xml.
_PARAM_FIELDS = [
    ("enabled", "wms_gdrive.enabled", "bool", "1"),
    ("manual_enabled", "wms_gdrive.manual_enabled", "bool", "1"),
    ("backup_time", "wms_gdrive.backup_time", "char", "16:30"),
    ("notify_success", "wms_gdrive.notify_success", "bool", "1"),
    ("notify_failure", "wms_gdrive.notify_failure", "bool", "1"),
    ("retention_daily_days", "wms_gdrive.retention_daily_days", "int", "30"),
    ("retention_weekly_months", "wms_gdrive.retention_weekly_months", "int", "6"),
    ("retention_monthly_years", "wms_gdrive.retention_monthly_years", "int", "2"),
    ("delete_manual", "wms_gdrive.delete_manual", "bool", "0"),
    ("folder_name", "wms_gdrive.folder_name", "char", "Inventory_Backups"),
]


class WmsGdriveSettings(models.TransientModel):
    _name = "wms.gdrive.settings"
    _description = "Google Drive backup settings"

    enabled = fields.Boolean(
        string="Upload backups to Google Drive",
        help="Soft kill-switch for the Drive stage. The token file written "
        "by scripts/setup-gdrive-auth.ps1 is the hard gate: without it the "
        "stage stays silently disabled regardless of this flag.",
    )
    manual_enabled = fields.Boolean(
        string="Allow Backup Now",
        help="Whether the Backup Now wizard may trigger a manual backup.",
    )
    backup_time = fields.Char(
        string="Daily backup time",
        help="24h HH:MM, e.g. 16:30. Display + Apply-Schedule target; the "
        "Windows Task Scheduler is the executor.",
    )
    notify_success = fields.Boolean(
        string="Notify managers on successful upload",
    )
    notify_failure = fields.Boolean(
        string="Notify managers on failure / staleness",
    )
    retention_daily_days = fields.Integer(
        string="Keep every daily set (days)",
        help="Drive retention tier 1: every set younger than this is kept.",
    )
    retention_weekly_months = fields.Integer(
        string="Keep one set per week (months)",
        help="Drive retention tier 2: newest set per ISO-week.",
    )
    retention_monthly_years = fields.Integer(
        string="Keep one set per month (years)",
        help="Drive retention tier 3: newest set per calendar month.",
    )
    delete_manual = fields.Boolean(
        string="Apply retention to manual / emergency sets",
        help="Off (default): manual and pre-restore emergency sets are "
        "never auto-deleted from Drive.",
    )
    folder_name = fields.Char(
        string="Drive folder name",
        help="Root folder on Google Drive holding the backup tree.",
    )
    health_html = fields.Html(readonly=True, sanitize=False)
    result_html = fields.Html(readonly=True, sanitize=False)

    # --- Load / save ---------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        param = self.env["ir.config_parameter"].sudo()
        for fname, key, ftype, default in _PARAM_FIELDS:
            if fname not in fields_list:
                continue
            raw = param.get_param(key, default)
            if ftype == "bool":
                res[fname] = str(raw).strip() in _TRUE
            elif ftype == "int":
                try:
                    res[fname] = int(str(raw).strip())
                except ValueError:
                    res[fname] = int(default)
            else:
                res[fname] = raw
        if "health_html" in fields_list:
            res["health_html"] = self._health_strip_html()
        return res

    def action_save(self):
        self.ensure_one()
        self._check_manager()
        self._validate()
        param = self.env["ir.config_parameter"].sudo()
        for fname, key, ftype, _default in _PARAM_FIELDS:
            value = self[fname]
            if ftype == "bool":
                param.set_param(key, "1" if value else "0")
            else:
                param.set_param(key, str(value))
        self.write({"result_html": Markup("<p><b>Settings saved.</b></p>")})
        return self._reopen()

    def _validate(self):
        for fname, label in (
            ("retention_daily_days", "daily"),
            ("retention_weekly_months", "weekly"),
            ("retention_monthly_years", "monthly"),
        ):
            if self[fname] <= 0:
                raise UserError(
                    "The %s retention value must be a whole number greater "
                    "than zero (got %s)." % (label, self[fname])
                )
        if not _TIME_RE.match(self.backup_time or ""):
            raise UserError(
                "The daily backup time must be 24h HH:MM, e.g. 16:30 "
                "(got %r)." % (self.backup_time or "")
            )
        if not (self.folder_name or "").strip():
            raise UserError("The Drive folder name cannot be empty.")

    # --- Test Connection / Test Upload ---------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        self._check_manager()
        result = self._run_gdrive_test("connection")
        self.write({"result_html": self._render_test_result("connection", result)})
        return self._reopen()

    def action_test_upload(self):
        self.ensure_one()
        self._check_manager()
        result = self._run_gdrive_test("upload")
        self.write({"result_html": self._render_test_result("upload", result)})
        return self._reopen()

    def _run_gdrive_test(self, mode):
        """Run scripts/gdrive-test.ps1 -Mode <mode>; return its JSON dict.

        Isolated as the test seam (tests stub it or patch subprocess.run).
        ``mode`` only ever comes from the two fixed action strings above
        and the script validates it again with a ValidateSet.
        """
        script = self._gdrive_test_script_path()
        if not os.path.isfile(script):
            return {
                "ok": False,
                "error": "scripts/gdrive-test.ps1 is missing on this server.",
                "auth_expired": False,
            }
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script,
                    "-Mode",
                    mode,
                ],
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _logger.warning("gdrive-test.ps1 (%s) could not run: %s", mode, exc)
            return {"ok": False, "error": str(exc), "auth_expired": False}
        out = (proc.stdout or b"").decode("utf-8", "replace")
        # The script prints exactly ONE JSON object on stdout; scan from the
        # end so a stray banner line can never shadow it.
        for line in reversed(out.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except ValueError:
                    break
        _logger.warning(
            "gdrive-test.ps1 (%s) rc=%s produced no JSON: %r", mode, proc.returncode, out[:500]
        )
        return {
            "ok": False,
            "error": "The test script returned no readable result "
            "(see the Odoo log for detail).",
            "auth_expired": False,
        }

    def _gdrive_test_script_path(self):
        # Project root derived from the module location, the same trick as
        # wms.backup.audit._backup_dir(): .../wms_reports/wizard -> root.
        here = os.path.dirname(os.path.abspath(__file__))
        project = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        return os.path.join(project, "scripts", "gdrive-test.ps1")

    def _render_test_result(self, mode, result):
        if result.get("ok") and mode == "connection":
            html = Markup("<p><b>Connected.</b> Google Drive account: %s</p>") % (
                result.get("email") or "?"
            )
            used = result.get("used_mb")
            limit = result.get("limit_mb")
            if used is not None and limit:
                pct = min(100.0, 100.0 * float(used) / float(limit))
                html += Markup(
                    "<p>Storage: %.1f of %.1f GB used (%.0f%%)</p>"
                    "<div style='background:#e5e7eb;border-radius:4px;"
                    "height:10px;max-width:360px'>"
                    "<div style='background:%s;border-radius:4px;height:10px;"
                    "width:%.0f%%'></div></div>"
                ) % (
                    float(used) / 1024.0,
                    float(limit) / 1024.0,
                    pct,
                    "#b91c1c" if pct >= 90 else "#15803d",
                    pct,
                )
            if result.get("folder_ok"):
                html += Markup("<p>Backup folder is reachable.</p>")
            return html
        if result.get("ok"):
            return Markup(
                "<p><b>Test upload OK.</b> %s (round-trip %s ms). The test "
                "file was verified on Drive and deleted again.</p>"
            ) % (result.get("file") or "?", result.get("roundtrip_ms") or "?")
        html = Markup("<p><b>Test failed:</b> %s</p>") % (result.get("error") or "unknown error")
        if result.get("auth_expired"):
            html += Markup(
                "<p>Google authorization has expired. Run "
                "<code>scripts\\setup-gdrive-auth.ps1</code> on the server to "
                "re-connect — and make sure the Google consent screen is "
                "published to <b>Production</b>, otherwise the token dies "
                "every 7 days.</p>"
            )
        return html

    # --- Apply Schedule -------------------------------------------------------
    def action_apply_schedule(self):
        """Best-effort ``schtasks /Change`` on the daily task. Never lets a
        scheduler failure escape — the fallback instruction is shown
        inline instead (the param is saved either way so the script and
        the display stay in sync)."""
        self.ensure_one()
        self._check_manager()
        if not _TIME_RE.match(self.backup_time or ""):
            raise UserError(
                "The daily backup time must be 24h HH:MM, e.g. 16:30 "
                "(got %r)." % (self.backup_time or "")
            )
        self.env["ir.config_parameter"].sudo().set_param("wms_gdrive.backup_time", self.backup_time)
        rc, detail = self._run_schtasks_change(self.backup_time)
        if rc != 0:
            _logger.warning(
                "Apply Schedule: schtasks /Change %r failed rc=%s: %s",
                DAILY_TASK_NAME,
                rc,
                detail,
            )
            self.write(
                {
                    "result_html": Markup(
                        "<p><b>Could not change the scheduled task.</b></p>"
                        "<p>Run <code>scripts\\install-backup-tasks.ps1 "
                        "-BackupAt %s</code> on the server instead. The "
                        "configured time was saved.</p>"
                    )
                    % self.backup_time,
                }
            )
        else:
            self.write(
                {
                    "result_html": Markup("<p><b>Daily backup re-scheduled to %s.</b></p>")
                    % self.backup_time,
                }
            )
        return self._reopen()

    def _run_schtasks_change(self, hhmm):
        """Subprocess seam (same shape as the Backup Now wizard's): with
        context key ``test_skip_schtasks`` nothing is spawned. ``hhmm``
        is regex-validated by the caller before it gets here."""
        if self.env.context.get("test_skip_schtasks"):
            return 0, ""
        try:
            proc = subprocess.run(
                ["schtasks.exe", "/Change", "/TN", DAILY_TASK_NAME, "/ST", hhmm],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, str(exc)
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        return proc.returncode, detail

    # --- Health strip (P13 surface for admins) --------------------------------
    def _health_strip_html(self):
        """Render _health_snapshot() Drive fields. Best-effort: the strip
        must never block the settings page. The gdrive_* keys appear once
        the health/cron chunk extends _health_snapshot (spec section 5.1);
        .get() keeps this forward-compatible until then, with the
        wms_gdrive.last_about cache as the storage fallback."""
        try:
            snap = self.env["wms.backup.audit"].sudo()._health_snapshot()
        except Exception:  # noqa: BLE001 - a probe error must not break the page
            return ""
        try:
            parts = [Markup("<b>Backup health:</b> %s") % (snap.get("status") or "?")]
            if snap.get("last_backup_age_hours") is not None:
                parts.append(Markup("last local backup %.1f h ago") % snap["last_backup_age_hours"])
            if snap.get("drive_connected") is not None:
                parts.append(
                    Markup("Drive %s")
                    % ("connected" if snap["drive_connected"] else "NOT connected")
                )
            if snap.get("last_upload_age_hours") is not None:
                parts.append(Markup("last Drive upload %.1f h ago") % snap["last_upload_age_hours"])
            if snap.get("next_backup_at"):
                parts.append(Markup("next backup %s") % snap["next_backup_at"])
            used = snap.get("drive_storage_used_mb")
            limit = snap.get("drive_storage_limit_mb")
            if used is None or not limit:
                used, limit = self._last_about_storage()
            if used is not None and limit:
                parts.append(
                    Markup("Drive storage %.1f / %.1f GB")
                    % (float(used) / 1024.0, float(limit) / 1024.0)
                )
            joined = Markup(" &#183; ").join(parts)
            return (
                Markup(
                    "<div class='alert alert-light' role='status' "
                    "style='border:1px solid #e5e7eb'>%s</div>"
                )
                % joined
            )
        except Exception:  # noqa: BLE001
            return ""

    def _last_about_storage(self):
        """(used_mb, limit_mb) from the wms_gdrive.last_about JSON cache
        written by test/upload runs, or (None, None)."""
        raw = self.env["ir.config_parameter"].sudo().get_param("wms_gdrive.last_about", "")
        try:
            about = json.loads(raw)
            return about.get("used_mb"), about.get("limit_mb")
        except (ValueError, TypeError, AttributeError):
            return None, None

    # --- Guards / plumbing ----------------------------------------------------
    def _check_manager(self):
        """Defense-in-depth group re-check (the menu + ACL already gate)."""
        if self.env.su:
            return
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise AccessError("Only WMS managers can change backup settings.")

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Google Drive Backup Settings",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

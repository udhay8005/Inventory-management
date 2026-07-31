# -*- coding: utf-8 -*-
"""Admin "Backup & Disaster Recovery" page (P1/P12, v18 DR page).

No res.config.settings exists anywhere in this project; the house
pattern is namespaced raw ir.config_parameter values read with
``.sudo().get_param()`` (D9). This TransientModel is the friendly face
over the ``wms_gdrive.*`` namespace: ``default_get`` loads the params,
``action_save`` writes them back. The parameters double as the
PowerShell pipeline's remote config (Get-WmsConfigParam in
scripts/gdrive-lib.ps1 reads them via psql with failure-safe defaults,
so a down DB never blocks a local backup).

Test Connection / Validate Folder / Disconnect shell out to the SAME
PowerShell stack the nightly pipeline uses (one credential path, one
retry policy, D2/D5) — gdrive-test.ps1 and setup-gdrive-auth.ps1 — and
parse their single JSON / textual stdout. Retry Now fires the
trigger-less "WMS Pending Upload Sweep" task via the same ``schtasks
/Run`` seam as Backup Now (heavy work runs as SYSTEM, never here).

CREDENTIAL BOUNDARY (HARD CONSTRAINT, spec section 7): the page is
*incapable* of touching the OAuth client secret or the DPAPI refresh
token. It NEVER accepts, displays, stores, or logs a raw secret. The
Client ID / Client Secret / refresh token are rendered as read-only
presence-only status; Service-Account JSON renders an explicit
"not supported" note; Access-Token status is derived purely from the
health snapshot + the last connection-test JSON. The only things that
leave the page toward the OS are fixed -Mode strings, a regex-validated
HH:MM, a charset-validated bare folder id, a schtasks /Run|/Change of
fixed task names, and a -Revoke switch.

Security: manager-only by three independent gates — the menu
(group_wms_manager), the model ACL (manager full CRUD on the
transient), AND a defense-in-depth ``_check_manager`` re-check at the
top of EVERY action. A storekeeper cannot reach this page. Subprocess
calls use argument arrays with fixed task/script names and a mode
string from a fixed set — wizard inputs never reach the command line.
"""
import json
import logging
import os
import re
import subprocess

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models.wms_backup_audit import PENDING_SWEEP_TASK_NAME

_logger = logging.getLogger(__name__)

# Fixed Scheduled Task name registered by scripts/install-backup-tasks.ps1.
DAILY_TASK_NAME = "WMS Daily Backup"

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# Bare Drive folder id: same charset Get-GDriveFolderInfo / the gdrive-test.ps1
# -FolderId ValidatePattern accept (spec section 2 / 4.7).
_FOLDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
# Folder-URL -> bare-id extraction for the three forms AREA 3 names
# (folders/<id>, /d/<id>, ?id=<id>). The raw URL never reaches PowerShell.
_FOLDER_URL_RE = re.compile(r"(?:folders/|/d/|[?&]id=)([A-Za-z0-9_-]{10,})")
_TRUE = ("1", "true", "True", "yes", "on")

# (field name, ir.config_parameter key, type, seeded default) — mirrors
# spec section 2 / data/gdrive_params.xml.
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
    # v18 offline-queue tuning (spec section 2). default_get / action_save
    # loop these automatically; _validate() enforces the int>0 / id-regex rules.
    ("offline_retry_max", "wms_gdrive.offline_retry_max", "int", "8"),
    ("offline_retry_window_days", "wms_gdrive.offline_retry_window_days", "int", "14"),
    ("offline_retry_max_per_run", "wms_gdrive.offline_retry_max_per_run", "int", "5"),
    ("offline_backoff_base_min", "wms_gdrive.offline_backoff_base_min", "int", "15"),
    ("parent_folder_id", "wms_gdrive.parent_folder_id", "char", ""),
]

# Credential presence is reported as a boolean only — the value is NEVER read
# into memory, displayed, stored, or logged (spec section 7). .env is written
# ONLY by setup-gdrive-auth.ps1 (via Set-DotEnvKey); the page just answers
# "is a non-placeholder value present?". Keys + placeholder pattern mirror
# Get-GDriveEnvConfig (gdrive-lib.ps1:275-292).
_CRED_ENV_KEYS = ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET")
# Same placeholder shapes Get-GDriveEnvConfig rejects (a placeholder counts as
# NOT configured, never "configured").
_PLACEHOLDER_RE = re.compile(r"^(changeme.*|your_.+_here|<.+>|x{3,}|todo.*)$", re.IGNORECASE)


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
    parent_folder_id = fields.Char(
        string="Drive folder ID",
        help="Optional Drive parent-folder id (the validated folder). Blank "
        "falls back to the .env GDRIVE_PARENT_FOLDER_ID then My Drive root. "
        "Auto-filled from the folder URL — paste a URL above and it is "
        "extracted here; the raw URL is never stored.",
    )
    folder_url = fields.Char(
        string="Drive folder URL",
        help="Paste a Google Drive folder URL; the folder id is extracted into "
        "the field below on change. The URL itself is NOT stored.",
    )
    offline_retry_max = fields.Integer(
        string="Max upload attempts",
        help="Max Drive upload attempts before a set is abandoned and surfaced "
        "to managers. Caps retry_count.",
    )
    offline_retry_window_days = fields.Integer(
        string="Retry window (days)",
        help="How far back the reconnect sweep looks for un-uploaded sets. "
        "Align with local retention so a kept file is never an orphan.",
    )
    offline_retry_max_per_run = fields.Integer(
        string="Max sets per sweep",
        help="Max sets retried per reconnect-sweep run (bounds the task's " "time budget).",
    )
    offline_backoff_base_min = fields.Integer(
        string="Backoff base (minutes)",
        help="Exponential-backoff base: next retry = now + base * 2^(attempt-1), " "capped at 24h.",
    )
    health_html = fields.Html(readonly=True, sanitize=False)
    result_html = fields.Html(readonly=True, sanitize=False)

    # --- Read-only display fields (computed in default_get; NEVER persisted,
    # NEVER a secret — spec sections 6.2 / 7). ------------------------------
    conn_status_html = fields.Html(
        readonly=True,
        sanitize=False,
        help="Connected / Not Connected + account email + auth-expired CTA, "
        "derived from the health snapshot and the last connection test.",
    )
    cred_presence_html = fields.Html(
        readonly=True,
        sanitize=False,
        help="Presence-only credential status (configured / NOT configured / "
        "present). Never shows a secret value.",
    )
    folder_validate_html = fields.Html(readonly=True, sanitize=False)
    schedule_tz_note = fields.Html(readonly=True, sanitize=False)
    queue_pending = fields.Integer(readonly=True, string="Pending uploads")
    queue_waiting = fields.Integer(readonly=True, string="Waiting for internet")
    queue_abandoned = fields.Integer(readonly=True, string="Abandoned (need attention)")
    queue_last_upload = fields.Datetime(readonly=True, string="Last Drive upload")
    queue_last_failure = fields.Datetime(readonly=True, string="Last upload failure")
    queue_last_failure_msg = fields.Char(readonly=True, string="Last failure detail")
    queue_max_retry = fields.Integer(readonly=True, string="Highest retry count")

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

        # Read-only display tier: one health snapshot drives all status
        # (spec section 5.3 — one source, do not fork).
        snap = self._safe_snapshot()
        if "conn_status_html" in fields_list:
            res["conn_status_html"] = self._conn_status_html(snap)
        if "cred_presence_html" in fields_list:
            res["cred_presence_html"] = self._cred_presence_html(snap)
        if "schedule_tz_note" in fields_list:
            res["schedule_tz_note"] = Markup(
                "<span class='text-muted'>Runs in the server's local time "
                "(Windows Task Scheduler is the executor). The next run time "
                "is shown in the health strip above.</span>"
            )
        # Offline-queue panel: search_count on the catalog + snapshot fields.
        if any(
            f in fields_list
            for f in (
                "queue_pending",
                "queue_waiting",
                "queue_abandoned",
                "queue_max_retry",
                "queue_last_upload",
                "queue_last_failure",
                "queue_last_failure_msg",
            )
        ):
            res.update(self._queue_panel_values(snap))
        return res

    @api.onchange("folder_url")
    def _onchange_folder_url(self):
        """Extract a bare folder id from a pasted Drive URL into
        ``parent_folder_id`` (folders/<id> | /d/<id> | ?id=<id>). The raw URL
        is NEVER stored — only the charset-safe bare id reaches PowerShell
        (spec sections 6.3 / 7)."""
        if not self.folder_url:
            return
        match = _FOLDER_URL_RE.search(self.folder_url)
        if match:
            self.parent_folder_id = match.group(1)

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
            ("offline_retry_max", "max upload attempts"),
            ("offline_retry_window_days", "retry window (days)"),
            ("offline_retry_max_per_run", "max sets per sweep"),
            ("offline_backoff_base_min", "backoff base (minutes)"),
        ):
            if self[fname] <= 0:
                raise UserError(
                    "The %s value must be a whole number greater "
                    "than zero (got %s)." % (label, self[fname])
                )
        if not _TIME_RE.match(self.backup_time or ""):
            raise UserError(
                "The daily backup time must be 24h HH:MM, e.g. 16:30 "
                "(got %r)." % (self.backup_time or "")
            )
        if not (self.folder_name or "").strip():
            raise UserError("The Drive folder name cannot be empty.")
        parent = (self.parent_folder_id or "").strip()
        if parent and not _FOLDER_ID_RE.match(parent):
            raise UserError(
                "The Drive folder ID looks invalid. Paste a Drive folder URL "
                "in the field above to fill it automatically, or leave it "
                "blank to use the default folder (got %r)." % parent
            )

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

    def action_refresh_token(self):
        """Prove the refresh token still works by re-running the connection
        test. There is nothing to "press refresh" on — Get-GDriveAccessToken
        auto-refreshes within 120s of expiry / on a 401, so a successful
        connection test IS live proof the token is healthy (spec section 7)."""
        self.ensure_one()
        self._check_manager()
        result = self._run_gdrive_test("connection")
        if result.get("ok"):
            html = Markup(
                "<p><b>Authorization is healthy.</b> The stored token was "
                "refreshed and accepted by Google.</p>"
            )
            html += self._render_test_result("connection", result)
        else:
            html = self._render_test_result("connection", result)
        self.write({"result_html": html})
        return self._reopen()

    def action_validate_folder(self):
        """Validate the configured Drive folder id via
        gdrive-test.ps1 -Mode validate-folder -FolderId <bare id>. Only the
        charset-validated bare id leaves the page (spec sections 4.7 / 7)."""
        self.ensure_one()
        self._check_manager()
        folder_id = (self.parent_folder_id or "").strip()
        if not folder_id:
            self.write(
                {
                    "folder_validate_html": Markup(
                        "<p class='text-muted'>No folder ID set — backups go to "
                        "the default folder (<code>%s</code>). Paste a Drive "
                        "folder URL above to target a specific folder.</p>"
                    )
                    % (self.folder_name or "My Drive root")
                }
            )
            return self._reopen()
        if not _FOLDER_ID_RE.match(folder_id):
            raise UserError(
                "The Drive folder ID looks invalid (got %r). Paste a Drive "
                "folder URL above to fill it automatically." % folder_id
            )
        result = self._run_gdrive_test("validate-folder", extra_args=["-FolderId", folder_id])
        self.write({"folder_validate_html": self._render_folder_validate(result)})
        return self._reopen()

    def action_disconnect(self):
        """Revoke the Drive authorization on this server (POSTs the refresh
        token to Google's revoke endpoint + deletes the DPAPI token file).
        No browser; honest server-side feasibility. Local backups are
        unaffected (spec section 7)."""
        self.ensure_one()
        self._check_manager()
        rc, detail = self._run_setup_auth(["-Revoke"])
        if rc == 0:
            html = Markup(
                "<p><b>Disconnected.</b> The Google Drive authorization on this "
                "server was revoked and the stored token deleted. Local "
                "encrypted backups continue to run unaffected.</p>"
                "<p>To re-connect, run "
                "<code>scripts\\setup-gdrive-auth.ps1</code> at the server "
                "console.</p>"
            )
        else:
            _logger.warning(
                "Disconnect: setup-gdrive-auth.ps1 -Revoke failed rc=%s: %s", rc, detail
            )
            html = Markup(
                "<p><b>Could not revoke automatically.</b> Run "
                "<code>scripts\\setup-gdrive-auth.ps1 -Revoke</code> at the "
                "server console instead. Local backups are unaffected.</p>"
            )
        self.write({"result_html": html})
        return self._reopen()

    def action_connect_help(self):
        """Guided console instruction ONLY — never a headless OAuth flow.
        Google's Desktop-app consent opens a real browser and hard-refuses the
        SYSTEM principal Odoo runs as, so it cannot complete from this page
        (spec section 7). We document the one-time console step honestly."""
        self.ensure_one()
        self._check_manager()
        self.write(
            {
                "result_html": Markup(
                    "<p><b>Connecting Google Drive is a one-time console "
                    "step.</b></p>"
                    "<p>On the WMS server, open PowerShell in the project "
                    "folder and run:</p>"
                    "<p><code>scripts\\setup-gdrive-auth.ps1</code></p>"
                    "<p>It opens a browser for Google consent and stores an "
                    "encrypted refresh token on the server. This cannot be "
                    "done from this page — the Google sign-in must happen at "
                    "the server. Publish the OAuth consent screen to "
                    "<b>Production</b> so the token does not expire every "
                    "7 days. See <code>docs/22-gdrive-backup.md</code>.</p>"
                )
            }
        )
        return self._reopen()

    def action_retry_now(self):
        """Fire the trigger-less 'WMS Pending Upload Sweep' task via the same
        schtasks /Run seam as Backup Now. The sweep probes connectivity itself
        and no-ops when still offline; heavy work runs as SYSTEM, never here
        (spec section 5.2). Graceful fallback if the task is absent."""
        self.ensure_one()
        self._check_manager()
        rc, detail = self._run_pending_sweep_task()
        if rc == 0:
            html = Markup(
                "<p><b>Retry started.</b> The server is re-attempting any "
                "pending Google Drive uploads in the background. If the "
                "internet is still down nothing happens and the sets stay "
                "queued — they will upload automatically once it returns.</p>"
            )
        else:
            _logger.warning(
                "Retry Now: schtasks /Run %r failed rc=%s: %s",
                PENDING_SWEEP_TASK_NAME,
                rc,
                detail,
            )
            html = (
                Markup(
                    "<p><b>Could not start the retry.</b> The '%s' scheduled task "
                    "is not installed on this server. Ask your administrator to "
                    "run <code>scripts\\install-backup-tasks.ps1</code> once. "
                    "Pending sets are still retried automatically every hour and "
                    "on the next daily run.</p>"
                )
                % PENDING_SWEEP_TASK_NAME
            )
        self.write({"result_html": html})
        return self._reopen()

    def _run_gdrive_test(self, mode, extra_args=None):
        """Run scripts/gdrive-test.ps1 -Mode <mode> [extra_args]; return its
        JSON dict.

        Isolated as the test seam (tests stub it or patch subprocess.run).
        ``mode`` only ever comes from the fixed action strings above and the
        script validates it again with a ValidateSet. ``extra_args`` (e.g.
        ``-FolderId <bare id>``) are built only from charset-validated values
        — no user free-text reaches the command line.
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
                ]
                + list(extra_args or []),
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

    def _project_root(self):
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(os.path.dirname(here)))

    # --- Disconnect / Retry-Now subprocess seams ------------------------------
    def _run_setup_auth(self, args):
        """Run scripts/setup-gdrive-auth.ps1 with the given fixed-switch args
        (only ``-Revoke`` is ever passed). Returns (rc, detail). With context
        key ``test_skip_schtasks`` nothing is spawned and success is reported,
        so the seam is zero-mock testable like the other subprocess gates."""
        if self.env.context.get("test_skip_schtasks"):
            return 0, ""
        script = os.path.join(self._project_root(), "scripts", "setup-gdrive-auth.ps1")
        if not os.path.isfile(script):
            return 1, "scripts/setup-gdrive-auth.ps1 is missing on this server."
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script,
                ]
                + list(args),
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, str(exc)
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        return proc.returncode, detail

    def _run_pending_sweep_task(self):
        """Fire the trigger-less 'WMS Pending Upload Sweep' task. Returns
        (rc, detail). Same ``schtasks /Run`` seam as
        wms.gdrive.backup.now._run_schtasks: with context key
        ``test_skip_schtasks`` the subprocess is never spawned and success is
        reported. Argument-array invocation only, fixed task-name constant —
        the injection surface is zero. A missing task surfaces as a non-zero
        rc the caller treats as a graceful no-op (never an exception)."""
        if self.env.context.get("test_skip_schtasks"):
            return 0, ""
        try:
            proc = subprocess.run(
                ["schtasks.exe", "/Run", "/TN", PENDING_SWEEP_TASK_NAME],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, str(exc)
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        return proc.returncode, detail

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

    def _render_folder_validate(self, result):
        """Render the validate-folder JSON (name/owner/accessible/writable).
        Secret-free by contract — the JSON never carries credential material
        (spec sections 4.7 / 7)."""
        if result.get("ok"):
            writable = result.get("writable")
            html = Markup(
                "<div class='alert alert-success' role='status'>"
                "<p><b>Folder is valid.</b></p>"
                "<p>Name: <b>%s</b><br/>Owner: %s<br/>Backups can be written "
                "here: <b>%s</b></p></div>"
            ) % (
                result.get("name") or "?",
                result.get("owner") or "?",
                "yes" if writable else "NO — this account cannot add files",
            )
            if not writable:
                html += Markup(
                    "<div class='alert alert-warning' role='status'>The folder "
                    "is visible but not writable by the backup account. Share "
                    "it with edit access, or leave the folder ID blank to use "
                    "the default folder.</div>"
                )
            return html
        html = Markup(
            "<div class='alert alert-danger' role='status'>"
            "<p><b>Folder check failed:</b> %s</p></div>"
        ) % (result.get("error") or "unknown error")
        if result.get("auth_expired"):
            html += Markup(
                "<div class='alert alert-warning' role='status'>Google "
                "authorization has expired — run "
                "<code>scripts\\setup-gdrive-auth.ps1</code> on the server to "
                "re-connect, then validate again.</div>"
            )
        return html

    # --- Read-only status renderers (NEVER a secret — spec section 7) --------
    def _safe_snapshot(self):
        """One health snapshot for every status field (one source, do not
        fork — spec section 5.3). Best-effort: a probe error never breaks
        the page."""
        try:
            return self.env["wms.backup.audit"].sudo()._health_snapshot() or {}
        except Exception:  # noqa: BLE001 - status must never break the page
            return {}

    def _conn_status_html(self, snap):
        """Connected / Not Connected indicator + account + auth-expired CTA,
        derived from _health_snapshot() (drive_connected / last_upload_age_hours)
        and the wms_gdrive.last_about cache. Never touches a secret."""
        if not snap.get("gdrive_enabled"):
            return Markup(
                "<div class='alert alert-secondary' role='status'>"
                "<b>Google Drive backup is off.</b> Local encrypted backups "
                "still run. Turn it on below and connect at the server "
                "console.</div>"
            )
        connected = bool(snap.get("drive_connected"))
        klass = "alert-success" if connected else "alert-warning"
        label = "Connected" if connected else "Not connected"
        parts = [Markup("<b>%s.</b>") % label]
        about = self._last_about_dict()
        email = about.get("email") if isinstance(about, dict) else None
        if email:
            parts.append(Markup("Account: %s") % email)
        age = snap.get("last_upload_age_hours")
        if age is not None:
            parts.append(Markup("last Drive upload %.1f h ago") % age)
        body = Markup(" &#183; ").join(parts)
        html = Markup("<div class='alert %s' role='status'>%s</div>") % (klass, body)
        if not connected:
            html += Markup(
                "<div class='alert alert-light' role='status' "
                "style='border:1px solid #e5e7eb'>If this server was just set "
                "up, or the token expired, run "
                "<code>scripts\\setup-gdrive-auth.ps1</code> at the server "
                "console (button <b>Connect…</b> shows the steps). Use "
                "<b>Test Connection</b> to verify.</div>"
            )
        return html

    def _last_about_dict(self):
        """The wms_gdrive.last_about JSON cache (account/quota), or {}. Written
        by test/upload runs — contains no secret."""
        raw = self.env["ir.config_parameter"].sudo().get_param("wms_gdrive.last_about", "")
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _cred_presence_html(self, snap):
        """Presence-ONLY credential status. Reports configured / NOT
        configured / present without EVER reading a secret value into a
        rendered string (spec section 7). Client ID/Secret presence comes
        from .env (written only by setup-gdrive-auth.ps1); the refresh token
        is a SYSTEM-only DPAPI blob whose mere file existence we report."""
        present = self._env_cred_present()
        token_present = self._token_file_present()

        def row(label, ok, present_word="configured"):
            colour = "#15803d" if ok else "#b91c1c"
            text = present_word if ok else "NOT configured"
            return Markup("<li>%s: <b style='color:%s'>%s</b></li>") % (label, colour, text)

        items = Markup("").join(
            [
                row("Client ID", present.get("GDRIVE_CLIENT_ID", False)),
                row("Client Secret", present.get("GDRIVE_CLIENT_SECRET", False)),
                row("Refresh token", token_present, "present (DPAPI, SYSTEM-only)"),
            ]
        )
        html = (
            Markup(
                "<div class='alert alert-light' role='status' "
                "style='border:1px solid #e5e7eb'>"
                "<p><b>Credentials (status only — values are never shown):</b></p>"
                "<ul style='margin-bottom:4px'>%s</ul>"
                "<p class='text-muted' style='margin-bottom:0'>Service-account "
                "JSON auth is not supported in this WMS build (OAuth Desktop + "
                "refresh token only). Credentials live in <code>.env</code> / an "
                "encrypted token on the server and are set there, never from this "
                "page.</p></div>"
            )
            % items
        )
        return html

    def _env_cred_present(self):
        """{key: bool} — whether each credential key in .env holds a
        non-placeholder value. The value itself is compared locally and
        discarded; it is NEVER returned, rendered, stored, or logged."""
        result = {key: False for key in _CRED_ENV_KEYS}
        env_path = os.path.join(self._project_root(), ".env")
        try:
            with open(env_path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, _, value = line.partition("=")
                    name = name.strip()
                    if name in result:
                        value = value.strip().strip("\"'")
                        result[name] = bool(value) and not _PLACEHOLDER_RE.match(value)
        except OSError:
            pass
        return result

    def _token_file_present(self):
        """Whether the encrypted refresh-token file exists. We only check
        existence — the DPAPI(LocalMachine) blob is readable by SYSTEM only,
        so the Odoo worker cannot (and must not) decrypt it."""
        token_path = os.path.join(self._project_root(), "config", "gdrive-token.json.dpapi")
        return os.path.isfile(token_path)

    def _queue_panel_values(self, snap):
        """Read-only offline-queue metrics: search_count on the catalog +
        the snapshot's queue keys (spec section 5.3). No new storage."""
        backup = self.env["wms.gdrive.backup"].sudo()
        pending_states = ("created", "waiting", "uploading", "failed")
        last_upload = self.env["wms.backup.audit"].sudo()._last_success("backup_gdrive")
        return {
            "queue_pending": backup.search_count([("queue_state", "in", pending_states)]),
            "queue_waiting": backup.search_count([("queue_state", "=", "waiting")]),
            "queue_abandoned": backup.search_count([("queue_state", "=", "abandoned")]),
            "queue_last_upload": last_upload.event_time if last_upload else False,
            "queue_last_failure": snap.get("last_failure_time") or False,
            "queue_last_failure_msg": snap.get("last_failure_message") or False,
            "queue_max_retry": snap.get("queue_max_retry") or 0,
        }

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
            "name": "Backup & Disaster Recovery",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

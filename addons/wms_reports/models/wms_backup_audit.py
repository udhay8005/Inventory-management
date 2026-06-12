# -*- coding: utf-8 -*-
"""Operational audit trail for backups + restore drills.

This is a LIGHTWEIGHT, append-only operational model — not a business
record. Rows are written by:

  * scripts/backup-native.ps1   (after each DB / filestore backup,
                                 and after each Google Drive upload)
  * scripts/restore-drill.ps1   (after each weekly restore drill)
  * scripts/gdrive-restore.ps1  (after each Drive download / restore)

Both PowerShell scripts INSERT directly via psql (they already hold the
DB connection), so the audit trail survives even when Odoo's HTTP layer
is down. Daily crons (_cron_check_backup_freshness,
_cron_check_gdrive_freshness) escalate staleness, an hourly cron
(_cron_notify_gdrive_events) turns the scripts' Drive rows into manager
Discuss notices, and the /wms/health controller reads _health_snapshot()
for monitoring.

No secrets are ever stored here — only filenames, sizes, checksums,
timings, and human-readable status messages.
"""
import json
import logging
import os
import shutil
from datetime import datetime, timedelta

from odoo import api, fields, models

from .wms_notify import notify_wms_managers

_logger = logging.getLogger(__name__)

# Thresholds (hours / days). Tunable in one place.
BACKUP_STALE_HOURS = 24
DRILL_STALE_DAYS = 7
DISK_FREE_MIN_MB = 1024  # warn when the backup volume drops below 1 GB free
# Google Drive upload staleness: daily cadence + 2h slack. DEGRADED-tier
# ONLY, never CRITICAL — the local artifact is THE backup; a cloud problem
# must not page like local-backup loss (spec section 10).
GDRIVE_STALE_HOURS = 26


class WmsBackupAudit(models.Model):
    _name = "wms.backup.audit"
    _description = "Backup & DR operational audit"
    _order = "event_time desc, id desc"

    name = fields.Char(
        required=True,
        index=True,
        help="Backup filename or drill label this event refers to.",
    )
    audit_type = fields.Selection(
        [
            ("backup_db", "Database backup"),
            ("backup_filestore", "Filestore backup"),
            ("backup_offsite", "Off-site copy"),
            ("backup_gdrive", "Google Drive upload"),
            ("restore_gdrive", "Google Drive restore"),
            ("restore_drill", "Restore drill"),
            ("staleness_warning", "Staleness warning"),
            ("health_critical", "Health CRITICAL escalation"),
        ],
        required=True,
        index=True,
    )
    success = fields.Boolean(
        default=False,
        index=True,
        help="True if the operation completed cleanly.",
    )
    notified = fields.Boolean(
        default=False,
        index=True,
        help="Internal: True once an alerting cron (restore-drill failure, "
        "health-critical, Drive events) has handled this row. Prevents "
        "repeat alerts.",
    )
    event_time = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        index=True,
        help="When the event occurred (UTC).",
    )
    duration_seconds = fields.Float(help="Wall-clock duration of the operation.")
    size_mb = fields.Float(help="Artifact size in MB (encrypted .gpg on disk).")
    toc_entries = fields.Integer(
        help="pg_restore --list table-of-contents entry count. A healthy "
        "Odoo dump has 1000+; a low number signals a truncated backup.",
    )
    verified = fields.Boolean(
        help="True if pg_restore --list confirmed the dump is structurally " "restorable.",
    )
    checksum = fields.Char(help="SHA-256 of the artifact (integrity reference).")
    host = fields.Char(help="Machine that produced the event.")
    message = fields.Text(help="Human-readable status / error detail.")

    # --- Helpers -----------------------------------------------------------
    @api.model
    def record_event(self, vals):
        """Thin create wrapper for callers that reach Odoo via XML-RPC.

        The PowerShell scripts INSERT directly via psql and do NOT use
        this path, but it keeps an ORM-friendly door open for tests and
        future integrations. sudo() so an unprivileged service user can
        still log an event.
        """
        return self.sudo().create(vals)

    @api.model
    def _last_success(self, audit_type):
        """Return the most recent successful record of a given type."""
        return self.sudo().search(
            [("audit_type", "=", audit_type), ("success", "=", True)],
            order="event_time desc",
            limit=1,
        )

    @api.model
    def _backup_dir(self):
        """Absolute path of the backups directory the PowerShell scripts write
        to. Override with the `wms_reports.backup_dir` system parameter; else
        derive <project>/backups from this module's location."""
        param = self.env["ir.config_parameter"].sudo().get_param("wms_reports.backup_dir")
        if param:
            return param
        here = os.path.dirname(os.path.abspath(__file__))  # .../wms_reports/models
        project = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        return os.path.join(project, "backups")

    @api.model
    def _health_snapshot(self):
        """Return a non-sensitive operational health dict.

        Status escalation: HEALTHY < DEGRADED < CRITICAL.
          * CRITICAL — no successful DB backup has ever been recorded.
          * DEGRADED — backup older than BACKUP_STALE_HOURS, OR no/older
            restore drill than DRILL_STALE_DAYS.
          * HEALTHY  — fresh backup and a recent drill.

        Critical #8: this probes REALITY, not just the audit table - it runs a
        live DB query, checks the most recent recorded backup still EXISTS on
        disk, and checks free disk on the backup volume, so it can no longer
        report HEALTHY while backups have silently rotted (file deleted, disk
        full) nor stay blind to a half-broken DB cursor.

        Google Drive (P13): when the off-site Drive tier is live
        (wms_gdrive.enabled != '0' AND an upload row or about-cache exists)
        the snapshot grows gdrive_enabled / drive_connected /
        last_upload_age_hours / drive_storage_used_mb /
        drive_storage_limit_mb / next_backup_at; otherwise only
        gdrive_enabled=False. Drive problems escalate to DEGRADED at most -
        NEVER CRITICAL (the local artifact is the backup that pages).
        """
        now = fields.Datetime.now()
        warnings = []
        rank = {"HEALTHY": 0, "DEGRADED": 1, "CRITICAL": 2}
        status = "HEALTHY"

        def escalate(level):
            nonlocal status
            if rank[level] > rank[status]:
                status = level

        last_backup = self._last_success("backup_db")
        if not last_backup:
            escalate("CRITICAL")
            warnings.append("no successful database backup on record")
            backup_age_hours = None
        else:
            backup_age_hours = (now - last_backup.event_time).total_seconds() / 3600.0
            if backup_age_hours > BACKUP_STALE_HOURS:
                escalate("DEGRADED")
                warnings.append(
                    "last database backup is %.1fh old (> %dh)"
                    % (backup_age_hours, BACKUP_STALE_HOURS)
                )

        last_drill = self._last_success("restore_drill")
        if not last_drill:
            escalate("DEGRADED")
            warnings.append("no successful restore drill on record")
            drill_age_days = None
        else:
            drill_age_days = (now - last_drill.event_time).total_seconds() / 86400.0
            if drill_age_days > DRILL_STALE_DAYS:
                escalate("DEGRADED")
                warnings.append(
                    "last restore drill is %.1fd old (> %dd)" % (drill_age_days, DRILL_STALE_DAYS)
                )

        # --- Critical #8: probe reality, not just the audit table ----------
        db_reachable = True
        try:
            self.env.cr.execute("SELECT 1")
            self.env.cr.fetchone()
        except Exception:  # noqa: BLE001 - any failure means not reachable
            db_reachable = False
            escalate("CRITICAL")
            warnings.append("database query probe failed")

        backup_dir = self._backup_dir()
        backup_file_present = None
        if last_backup and last_backup.name and os.path.isdir(backup_dir):
            backup_file_present = os.path.isfile(os.path.join(backup_dir, last_backup.name))
            if not backup_file_present:
                escalate("CRITICAL")
                warnings.append("the most recent recorded backup is missing from disk")

        if os.path.isdir(backup_dir):
            try:
                free_mb = shutil.disk_usage(backup_dir).free / (1024.0 * 1024.0)
                if free_mb < DISK_FREE_MIN_MB:
                    escalate("DEGRADED")
                    warnings.append("low free disk on the backup volume")
            except OSError:
                pass

        # --- Google Drive off-site tier (P13): DEGRADED only, NEVER
        # CRITICAL — CRITICAL stays reserved for the local pipeline.
        drive = self._gdrive_snapshot_fields(now)
        for warning in drive.pop("warnings"):
            escalate("DEGRADED")
            warnings.append(warning)

        snapshot = {
            "status": status,
            "db_reachable": db_reachable,
            "backup_file_present": backup_file_present,
            "last_backup_age_hours": (
                round(backup_age_hours, 1) if backup_age_hours is not None else None
            ),
            "last_drill_age_days": (
                round(drill_age_days, 1) if drill_age_days is not None else None
            ),
            "warnings": warnings,
        }
        snapshot.update(drive)
        return snapshot

    @api.model
    def _gdrive_snapshot_fields(self, now):
        """Google Drive fields for _health_snapshot() (spec section 5.1).

        Returns the gdrive_* snapshot keys plus a "warnings" list the
        caller folds in. Contract: every warning here is DEGRADED-level —
        this helper must never drive CRITICAL (Drive is the off-site tier;
        the local artifact is what pages).

        Computed only when the Drive tier is live: wms_gdrive.enabled !=
        '0' AND (a backup_gdrive audit row exists OR the
        wms_gdrive.last_about cache is populated). Otherwise only
        {"gdrive_enabled": False}, so a dark or kill-switched Drive stage
        can never degrade health.
        """
        param = self.env["ir.config_parameter"].sudo()
        enabled = (param.get_param("wms_gdrive.enabled", "1") or "").strip() != "0"
        about = self._gdrive_last_about()
        has_rows = bool(self.sudo().search_count([("audit_type", "=", "backup_gdrive")], limit=1))
        if not enabled or not (has_rows or about):
            return {"gdrive_enabled": False, "warnings": []}

        warnings = []
        upload_age_hours = None
        last_ok = self._last_success("backup_gdrive")
        if last_ok:
            upload_age_hours = (now - last_ok.event_time).total_seconds() / 3600.0
            if upload_age_hours > GDRIVE_STALE_HOURS:
                warnings.append("Google Drive upload is stale (%.0fh)" % upload_age_hours)
        else:
            warnings.append("no successful Google Drive upload on record")

        # Auth expiry (F6): the script writes GDRIVE_AUTH_EXPIRED into the
        # failure message on invalid_grant. Only the NEWEST row counts — a
        # success after the failure means the operator re-consented.
        newest = self.sudo().search(
            [("audit_type", "=", "backup_gdrive")],
            order="event_time desc, id desc",
            limit=1,
        )
        if newest and not newest.success and "GDRIVE_AUTH_EXPIRED" in (newest.message or ""):
            warnings.append("Google Drive auth expired")

        used_mb = limit_mb = about_age_hours = None
        if about:
            try:
                if about.get("used_mb") is not None:
                    used_mb = float(about["used_mb"])
                if about.get("limit_mb") is not None:
                    limit_mb = float(about["limit_mb"])
            except (TypeError, ValueError):
                used_mb = limit_mb = None
            checked = self._parse_about_checked_utc(about)
            if checked is not None:
                about_age_hours = (now - checked).total_seconds() / 3600.0
            if used_mb is not None and limit_mb and used_mb / limit_mb >= 0.9:
                warnings.append(
                    "Google Drive storage above 90%% (%.1f/%.1f GB)"
                    % (used_mb / 1024.0, limit_mb / 1024.0)
                )

        connected = bool(
            (upload_age_hours is not None and upload_age_hours <= GDRIVE_STALE_HOURS)
            or (about_age_hours is not None and about_age_hours <= GDRIVE_STALE_HOURS)
        )
        return {
            "gdrive_enabled": True,
            "drive_connected": connected,
            "last_upload_age_hours": (
                round(upload_age_hours, 1) if upload_age_hours is not None else None
            ),
            "drive_storage_used_mb": used_mb,
            "drive_storage_limit_mb": limit_mb,
            "next_backup_at": self._gdrive_next_backup_at(),
            "warnings": warnings,
        }

    @api.model
    def _gdrive_last_about(self):
        """Parsed wms_gdrive.last_about JSON cache ({used_mb, limit_mb,
        checked_utc, email}, written by the script's test/upload runs via
        psql) — or None when blank/unparseable."""
        raw = (
            self.env["ir.config_parameter"].sudo().get_param("wms_gdrive.last_about", "") or ""
        ).strip()
        if not raw:
            return None
        try:
            about = json.loads(raw)
        except ValueError:
            return None
        return about if isinstance(about, dict) else None

    @staticmethod
    def _parse_about_checked_utc(about):
        """Naive-UTC datetime from last_about's checked_utc (the script
        writes ISO-8601 UTC, e.g. '2026-06-12T11:30:00Z'); None when
        missing/unparseable."""
        raw = str(about.get("checked_utc") or "").replace("T", " ").rstrip("Z")[:19]
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    @api.model
    def _gdrive_next_backup_at(self):
        """'YYYY-MM-DD HH:MM' of the next scheduled backup run: today or
        tomorrow at wms_gdrive.backup_time. SERVER-LOCAL time on purpose —
        the Windows Task Scheduler (the executor) runs in local time,
        unlike the UTC audit timestamps. None when the param is
        unparseable."""
        raw = (
            self.env["ir.config_parameter"].sudo().get_param("wms_gdrive.backup_time", "16:30")
            or ""
        ).strip()
        try:
            hour_s, minute_s = raw.split(":")
            hour, minute = int(hour_s), int(minute_s)
        except ValueError:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        now_local = datetime.now()
        nxt = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if nxt <= now_local:
            nxt += timedelta(days=1)
        return nxt.strftime("%Y-%m-%d %H:%M")

    @api.model
    def _cron_check_backup_freshness(self):
        """Daily cron: escalate stale backups into an append-only warning
        row + a manager Discuss notice. Quiet when healthy."""
        snap = self._health_snapshot()
        if snap["status"] == "HEALTHY":
            _logger.info("wms.backup.audit: backup health HEALTHY")
            return

        detail = "; ".join(snap["warnings"]) or snap["status"]

        # Avoid spamming: at most one staleness warning row per ~day.
        cutoff = fields.Datetime.now() - timedelta(hours=20)
        recent = self.sudo().search_count(
            [
                ("audit_type", "=", "staleness_warning"),
                ("event_time", ">=", cutoff),
            ]
        )
        if not recent:
            self.sudo().create(
                {
                    "name": "freshness-check",
                    "audit_type": "staleness_warning",
                    "success": False,
                    "event_time": fields.Datetime.now(),
                    "message": "Backup health %s: %s" % (snap["status"], detail),
                    "host": "odoo-cron",
                }
            )

        _logger.warning("wms.backup.audit: backup health %s — %s", snap["status"], detail)
        self._notify_managers(snap["status"], detail)

    @api.model
    def _cron_check_restore_drill(self):
        """Notify managers when a restore drill row landed with success=False.

        Closes the silent-failure gap: restore-drill.ps1 already records
        successes and failures, but until now nobody was told - the manager
        had to open the audit report to discover the drill failed. This cron
        scans the latest restore_drill rows in the last 24h and pings managers
        for each failure (suppressed if a notice for the same row already
        fired - we mark the row's audit_type so the join is cheap).
        """
        cutoff = fields.Datetime.now() - timedelta(hours=24)
        fails = self.sudo().search(
            [
                ("audit_type", "=", "restore_drill"),
                ("success", "=", False),
                ("event_time", ">=", cutoff),
                ("notified", "=", False),
            ]
        )
        if not fails:
            return
        for row in fails:
            from markupsafe import Markup

            body = Markup(
                "<p>&#9888; <b>Restore drill FAILED.</b></p>"
                "<p>%s</p><p><i>Host:</i> %s &#183; <i>When:</i> %s</p>"
                "<p>Open <i>WMS &#8594; Reports &#8594; Backup &amp; DR Audit</i> "
                "to investigate.</p>"
            ) % (row.message or "(no detail)", row.host or "?", row.event_time)
            notify_wms_managers(self.env, body, "WMS - Restore drill FAILED")
        fails.write({"notified": True})

    @api.model
    def _cron_escalate_health_critical(self):
        """Escalate a CRITICAL health snapshot to managers immediately. The
        existing freshness cron only fires once a day at 08:00; CRITICAL is too
        important to wait that long. Runs every 4h, idempotent via the same
        20h dedupe used for staleness warnings."""
        snap = self._health_snapshot()
        if snap["status"] != "CRITICAL":
            return
        cutoff = fields.Datetime.now() - timedelta(hours=20)
        recent = self.sudo().search_count(
            [
                ("audit_type", "=", "health_critical"),
                ("event_time", ">=", cutoff),
            ]
        )
        if recent:
            return
        self.sudo().create(
            {
                "name": "health-critical",
                "audit_type": "health_critical",
                "success": False,
                "event_time": fields.Datetime.now(),
                "message": "Health CRITICAL: %s" % ("; ".join(snap["warnings"]) or "no detail"),
                "host": "odoo-cron",
            }
        )
        self._notify_managers("CRITICAL", "; ".join(snap["warnings"]) or "no detail")

    @api.model
    def _cron_check_gdrive_freshness(self):
        """Daily cron (08:05): Google Drive upload staleness -> one
        staleness_warning row + a manager Discuss notice, deduped to one
        per ~20h. DEGRADED-tier by design: this cron never writes
        health_critical rows — a cloud problem must not page like
        local-backup loss (the local freshness/CRITICAL crons own that).

        The dedupe is scoped by name='gdrive-freshness-check' so it can
        never swallow (or be swallowed by) the local freshness cron's
        'freshness-check' rows.
        """
        param = self.env["ir.config_parameter"].sudo()
        if (param.get_param("wms_gdrive.enabled", "1") or "").strip() == "0":
            return
        about = (param.get_param("wms_gdrive.last_about", "") or "").strip()
        has_rows = bool(self.sudo().search_count([("audit_type", "=", "backup_gdrive")], limit=1))
        if not (has_rows or about):
            return  # the Drive stage is dark (never set up) — nothing to warn about

        now = fields.Datetime.now()
        last_ok = self._last_success("backup_gdrive")
        if last_ok:
            age_hours = (now - last_ok.event_time).total_seconds() / 3600.0
            if age_hours <= GDRIVE_STALE_HOURS:
                _logger.info("wms.backup.audit: drive upload fresh (%.1fh)", age_hours)
                return
            detail = "Google Drive upload is stale (%.0fh, > %dh)" % (
                age_hours,
                GDRIVE_STALE_HOURS,
            )
        else:
            detail = "no successful Google Drive upload on record"

        cutoff = now - timedelta(hours=20)
        recent = self.sudo().search_count(
            [
                ("audit_type", "=", "staleness_warning"),
                ("name", "=", "gdrive-freshness-check"),
                ("event_time", ">=", cutoff),
            ]
        )
        if recent:
            return
        self.sudo().create(
            {
                "name": "gdrive-freshness-check",
                "audit_type": "staleness_warning",
                "success": False,
                "event_time": now,
                "message": "Google Drive backup DEGRADED: %s" % detail,
                "host": "odoo-cron",
            }
        )
        _logger.warning("wms.backup.audit: %s", detail)
        if (param.get_param("wms_gdrive.notify_failure", "1") or "").strip() != "1":
            return
        from markupsafe import Markup

        body = (
            Markup(
                "<p>&#9888; <b>Google Drive backup is stale.</b></p><p>%s.</p>"
                "<p>Your local backups are unaffected. Open <i>WMS &rsaquo; Reports "
                "&rsaquo; Backup &amp; DR Audit</i> for detail.</p>"
            )
            % detail
        )
        notify_wms_managers(self.env, body, "WMS - Google Drive backup stale")

    @api.model
    def _cron_notify_gdrive_events(self):
        """Hourly cron (:25): turn un-notified backup_gdrive /
        restore_gdrive audit rows (psql-written by the scripts, which
        never speak HTTP) into manager Discuss notices (P5/P14), honoring
        the wms_gdrive.notify_success / notify_failure switches.

        Every examined row is marked notified=True — including rows whose
        notice was suppressed by a switch — so a later param flip cannot
        replay day-old events.
        """
        cutoff = fields.Datetime.now() - timedelta(hours=24)
        rows = self.sudo().search(
            [
                ("audit_type", "in", ("backup_gdrive", "restore_gdrive")),
                ("event_time", ">=", cutoff),
                ("notified", "=", False),
            ],
            order="event_time asc, id asc",
        )
        if not rows:
            return
        param = self.env["ir.config_parameter"].sudo()
        notify_success = (param.get_param("wms_gdrive.notify_success", "1") or "").strip() == "1"
        notify_failure = (param.get_param("wms_gdrive.notify_failure", "1") or "").strip() == "1"
        from markupsafe import Markup

        for row in rows:
            is_restore = row.audit_type == "restore_gdrive"
            noun = "Google Drive restore" if is_restore else "Google Drive upload"
            if row.success:
                if not notify_success:
                    continue
                body = Markup(
                    "<p>&#10003; <b>%s OK</b> &#8212; %s</p><p>%s</p>"
                    "<p><i>Host:</i> %s &#183; <i>When:</i> %s</p>"
                ) % (noun, row.name or "?", row.message or "", row.host or "?", row.event_time)
                subject = "WMS - %s OK" % noun
            else:
                if not notify_failure:
                    continue
                intact = "" if is_restore else " Local backup is intact."
                body = Markup(
                    "<p>&#9888; <b>%s FAILED</b> &#8212; %s.%s</p><p>%s</p>"
                    "<p>Open <i>WMS &rsaquo; Reports &rsaquo; Backup &amp; DR Audit</i> "
                    "to investigate.</p>"
                ) % (noun, row.name or "?", intact, row.message or "(no detail)")
                subject = "WMS - %s FAILED" % noun
            notify_wms_managers(self.env, body, subject)
        rows.write({"notified": True})

    @api.model
    def _notify_managers(self, status, detail):
        """Alert WMS managers about backup health. Delivered via the shared
        notify helper so the message actually lands in their Discuss Inbox +
        systray (the previous partner.message_post never did)."""
        from markupsafe import Markup

        body = Markup(
            "<p>&#9888; <b>Backup health: %s</b></p><p>%s</p>"
            "<p>Open <i>WMS &rsaquo; Reports &rsaquo; Backup &amp; DR Audit</i> for detail.</p>"
        ) % (status, detail)
        notify_wms_managers(self.env, body, "WMS - Backup health %s" % status)

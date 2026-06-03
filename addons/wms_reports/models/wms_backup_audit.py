# -*- coding: utf-8 -*-
"""Operational audit trail for backups + restore drills.

This is a LIGHTWEIGHT, append-only operational model — not a business
record. Rows are written by:

  * scripts/backup-native.ps1   (after each DB / filestore backup)
  * scripts/restore-drill.ps1   (after each weekly restore drill)

Both PowerShell scripts INSERT directly via psql (they already hold the
DB connection), so the audit trail survives even when Odoo's HTTP layer
is down. A daily cron (_cron_check_backup_freshness) escalates staleness,
and the /wms/health controller reads _health_snapshot() for monitoring.

No secrets are ever stored here — only filenames, sizes, checksums,
timings, and human-readable status messages.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Thresholds (hours / days). Tunable in one place.
BACKUP_STALE_HOURS = 24
DRILL_STALE_DAYS = 7


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
            ("restore_drill", "Restore drill"),
            ("staleness_warning", "Staleness warning"),
        ],
        required=True,
        index=True,
    )
    success = fields.Boolean(
        default=False,
        index=True,
        help="True if the operation completed cleanly.",
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
    def _health_snapshot(self):
        """Return a non-sensitive operational health dict.

        Status escalation: HEALTHY < DEGRADED < CRITICAL.
          * CRITICAL — no successful DB backup has ever been recorded.
          * DEGRADED — backup older than BACKUP_STALE_HOURS, OR no/older
            restore drill than DRILL_STALE_DAYS.
          * HEALTHY  — fresh backup and a recent drill.

        Reaching this code at all means the DB is reachable, so
        db_reachable is always True in the returned payload (the
        controller treats an exception as CRITICAL separately).
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

        return {
            "status": status,
            "db_reachable": True,
            "last_backup_age_hours": (
                round(backup_age_hours, 1) if backup_age_hours is not None else None
            ),
            "last_drill_age_days": (
                round(drill_age_days, 1) if drill_age_days is not None else None
            ),
            "warnings": warnings,
        }

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
    def _notify_managers(self, status, detail):
        """Best-effort Discuss notice to WMS managers. Never raises."""
        try:
            from markupsafe import Markup

            managers = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
            if not managers or not managers.all_user_ids:
                return
            body = Markup(
                "<p>⚠️ <b>Backup health: %s</b></p><p>%s</p>"
                "<p>Open <i>WMS → Reports → Backup &amp; DR Audit</i> for detail.</p>"
            ) % (status, detail)
            for user in managers.all_user_ids:
                user.partner_id.message_post(
                    body=body,
                    subject="WMS — Backup health %s" % status,
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )
        except Exception:  # noqa: BLE001 - notification must never break the cron
            _logger.exception("wms.backup.audit: manager notification failed")

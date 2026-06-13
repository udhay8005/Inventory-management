# -*- coding: utf-8 -*-
"""Google Drive backup catalog — one row per backup set (uploaded or pending).

COLUMN CONTRACT WARNING (paired psql writer)
============================================
Rows are UPSERTed directly via psql by ``Write-GDriveCatalogRow`` in
scripts/gdrive-lib.ps1 (the backup pipeline runs out of process under
Task Scheduler, so the catalog must survive even when Odoo's HTTP layer
is down), and scripts/gdrive-restore.ps1 bumps ``restored_count`` the
same way. The v18 offline-queue columns (queue_state / retry_count /
last_error / error_class / next_retry_at) are written by the same psql
path: ``Set-GDriveQueueFailure`` (backup-native.ps1) on every failed
upload, the Stage 5a pending sweep on each retry/abandon transition, and
``Send-GDriveBackupSet``'s success UPSERT (queue_state='uploaded'
alongside uploaded=true). Those writes BYPASS the ORM entirely,
therefore:

  * every column below is a plain stored field — no compute, no
    related, no onchange may ever be added to a column the script
    writes (year / month_label / day in particular look computable
    from backup_time but MUST stay plain);
  * the column list is API: any field rename / addition / removal MUST
    update ``Write-GDriveCatalogRow`` in scripts/gdrive-lib.ps1 in the
    same commit.

No secrets are ever stored here — filenames, Drive file ids, sizes,
checksums and human-readable metadata only (the GPG passphrase never
leaves the box and the artifacts on Drive are ciphertext).
"""

from odoo import api, fields, models


class WmsGdriveBackup(models.Model):
    _name = "wms.gdrive.backup"
    _description = "Google Drive backup catalog"
    _order = "backup_time desc, id desc"

    name = fields.Char(
        required=True,
        index=True,
        help="LOCAL database backup filename (audit-compatible), "
        "e.g. wms-20260612-163000.dump.gpg.",
    )
    set_stamp = fields.Char(
        index=True,
        help="Backup-set stamp 'yyyyMMdd-HHmmss' (the appProperties set_id on Drive).",
    )
    db_name = fields.Char(help="Database the set was dumped from.")
    backup_type = fields.Selection(
        [
            ("auto", "Automatic"),
            ("manual", "Manual"),
            ("emergency", "Pre-restore emergency"),
        ],
        default="auto",
    )
    backup_time = fields.Datetime(help="When the backup ran (UTC).")
    # year / month_label / day mirror the Drive folder tree for the
    # grouped restore browser. Plain columns written by the script
    # INSERT — NOT computed: psql bypasses the ORM.
    year = fields.Char(index=True, help="Drive year folder, e.g. '2026'.")
    month_label = fields.Char(index=True, help="Drive month folder, e.g. '06-June'.")
    day = fields.Char(index=True, help="Drive day folder, e.g. '2026-06-12'.")
    drive_name = fields.Char(
        help="Drive display name of the database artifact, "
        "e.g. WMS_DB_2026-06-12_16-30-00.dump.gpg.",
    )
    drive_file_id = fields.Char(help="Drive file id of the database artifact.")
    drive_folder = fields.Char(
        help="Day-folder path for display, e.g. Inventory_Backups/2026/06-June/2026-06-12.",
    )
    filestore_drive_id = fields.Char(
        help="Drive file id of the filestore artifact (empty when the filestore was skipped).",
    )
    size_mb = fields.Float(help="Encrypted database artifact size in MB.")
    checksum = fields.Char(help="SHA-256 of the database .dump.gpg artifact.")
    uploaded = fields.Boolean(
        default=False,
        help="False = pending: the local set exists but its Drive upload has not "
        "succeeded yet (the next run's pending sweep retries it).",
    )
    upload_time = fields.Datetime(help="When the Drive upload completed (UTC).")
    creator = fields.Char(help="Odoo login, 'system (scheduled)', or console user.")
    encrypted = fields.Boolean(default=True)
    wms_version = fields.Char(help="wms_reports version at backup time.")
    info_json = fields.Text(help="Full backup-info.json document for the set.")
    restored_count = fields.Integer(
        default=0,
        help="Times this set was restored (bumped by gdrive-restore.ps1 via psql UPDATE).",
    )
    # --- v18 offline-queue state (PLAIN STORED — psql-written, see contract above) ---
    queue_state = fields.Selection(
        [
            ("created", "Created"),  # local set exists, upload not yet attempted
            ("waiting", "Waiting for internet"),  # offline: queued, no connectivity
            (
                "uploading",
                "Uploading",
            ),  # transient in-flight marker (set by sweep before Send-GDriveBackupSet)
            ("uploaded", "Uploaded"),  # mirrors uploaded=true; terminal success
            ("failed", "Failed"),  # last attempt failed for a non-offline reason
            ("abandoned", "Abandoned"),  # aged past the retry window / max attempts; needs human
        ],
        default="created",
        index=True,
        help="Offline-queue lifecycle. 'uploaded' mirrors the boolean `uploaded` "
        "field (kept for the v17 sweep dedup + restore browser filter).",
    )
    retry_count = fields.Integer(
        default=0,
        help="Drive upload attempts made for this set (incremented by the pending "
        "sweep / reconnect cron each time Send-GDriveBackupSet is called and fails).",
    )
    last_error = fields.Char(
        help="Trimmed last Drive upload error message (no secrets — Send-GDriveFile "
        "and Invoke-GDriveApi never put credentials in messages).",
    )
    error_class = fields.Char(
        help="Last failure class from Get-GDriveErrorClass: offline / auth_expired / "
        "quota / server_error / client_error / unknown.",
    )
    next_retry_at = fields.Datetime(
        help="UTC earliest next retry (exponential backoff). NULL = retry on next sweep.",
    )
    # NOT part of the psql column contract: store=False means no DB column
    # exists, so Write-GDriveCatalogRow is unaffected (the no-compute rule
    # above only protects the script-written columns).
    restore_command = fields.Char(
        compute="_compute_restore_command",
        store=False,
        help="Copy-paste command for the restore browser: downloads + "
        "triple-verifies this set (run in PowerShell on the WMS server).",
    )

    def _compute_restore_command(self):
        for rec in self:
            rec.restore_command = (
                "scripts\\gdrive-restore.ps1 -SetStamp %s" % rec.set_stamp
                if rec.set_stamp
                else False
            )

    # --- Helpers -----------------------------------------------------------
    @api.model
    def record_set(self, vals):
        """Thin create wrapper (record_event() pattern on wms.backup.audit).

        The PowerShell scripts UPSERT directly via psql and do NOT use
        this path, but it keeps an ORM-friendly door open for tests and
        future integrations. sudo() so an unprivileged service user can
        still register a set.
        """
        return self.sudo().create(vals)

# SOP 11 — Backup, Restore Drill, Health Monitoring, and the Backup & DR Audit Screen

## Purpose
This procedure explains how the Admin protects the trust's data and proves it can be recovered:

- **Backup** — run `scripts/backup-native.ps1` to write an encrypted database dump and filestore archive, self-verified before the plaintext is shredded.
- **Restore drill** — run `scripts/restore-drill.ps1` weekly to prove the latest backup is recoverable *without touching production*.
- **Restore (real recovery)** — run `scripts/restore-native.ps1` to restore an encrypted backup onto a database when something actually goes wrong.
- **Health monitoring** — `GET /wms/health` returns a simple status a monitor can poll.
- **Backup & DR Audit screen** — the in-app dashboard where every backup and drill is recorded automatically.

A backup that has never been restored is not a backup. This SOP ties the three scripts to the in-app evidence that proves they ran.

## Who Uses It
- **WMS / Manager (Admin) / system operator.** The scripts run from PowerShell on the server; the **Backup & DR Audit** screen and the **Download / Restore** menu entries under **WMS → Configuration** are **Manager-only** (`group_wms_manager`).
- A **monitoring system** polls `/wms/health` (no login needed — the endpoint is public and returns only non-sensitive status).
- Read-only viewers and Store Keepers are not involved.

## Prerequisites
- Access to the server, a PowerShell window, and the project root (`D:\Udhay\projects\Inventory_mngt`).
- **gpg.exe** on PATH (or Gpg4win installed) — used for AES-256 encryption/decryption.
- **pg_dump**, **pg_restore**, and **psql** on PATH.
- A real **`BACKUP_PASSPHRASE`** set in the project `.env` — 24+ random characters, no whitespace, and **not** the placeholder `changeme_backup_passphrase`. Without this passphrase the `.gpg` files cannot be restored. **Store the passphrase OFF the server.**
- Postgres connection settings are read automatically from `config\odoo.native.conf` (host, port, user, password) — the trust often runs Postgres on a non-default port, so don't hard-code one.
- For the in-app audit rows to appear, the `wms_reports` addon must be installed (the scripts INSERT directly via psql; if the table is missing they log a note and continue — the backup/drill itself is unaffected).

## Step-by-Step Instructions

### A. Run a backup
1. Open PowerShell at the project root.
2. Run:
   ```powershell
   scripts\backup-native.ps1
   ```
   Optional parameters: `-DbName wms` (default `wms`), `-Retain 30` (keep the most recent N backups; default 14), `-Passphrase <SecureString>` (override `.env` for this run).
3. The script:
   - Dumps the database with `pg_dump -Fc` and pipes it straight into `gpg --symmetric --cipher-algo AES256` (the unencrypted dump only touches disk for milliseconds, then is shredded).
   - **Verifies** the dump with `pg_restore --list` and aborts if the table-of-contents has fewer than ~100 entries (a healthy Odoo dump has 1000+) — this catches silent truncation.
   - Zips and encrypts the filestore the same way.
   - Applies retention (deletes all but the most recent N, including the matching filestore zip).
   - Writes a `backup_db` (and `backup_filestore`) row into `wms_backup_audit` with size, checksum, TOC count, and `verified = true`.
4. Artifacts land in `.\backups\` as `wms-<timestamp>.dump.gpg` and `wms-<timestamp>-filestore.zip.gpg`.
5. *(Optional, in-app)* A Manager can also trigger a one-off encrypted DB download from **WMS → Configuration → Download encrypted backup** (streams a `.dump.gpg` from the browser). This is a convenience, not a replacement for the scheduled script.

### B. Run the weekly restore drill
1. Open PowerShell at the project root.
2. Run the cheap verification (default, DryRun = true — verifies the TOC, does **not** create a database):
   ```powershell
   scripts\restore-drill.ps1
   ```
   Or a full end-to-end test that restores into a throwaway DB and drops it afterwards:
   ```powershell
   scripts\restore-drill.ps1 -DryRun:$false
   ```
   Optional: `-BackupPath <path>` to drill a specific file (default: the newest `*.dump.gpg`); `-KeepDrillDb` to keep the throwaway DB for inspection (use sparingly).
3. The drill decrypts the latest backup to a temp file, runs `pg_restore --list` to confirm the TOC survives, and — in a full run — restores into a database named `wms_drill_<timestamp>`, probes `res_users`, then drops it. The plaintext temp file is always wiped, even on failure. It refuses to act unless the drill DB name matches the safe `wms_drill_<timestamp>` pattern, so it can never hit production.
4. It writes a `restore_drill` row into `wms_backup_audit` (in the production DB, where Odoo reads it) and logs to `.runtime\logs\restore-drill.log` (and the Windows Application Event Log if the `WMS_Backup_Drill` source is registered).
5. Exit codes: `0` OK, `1` backup missing, `2` decrypt failed, `3` TOC failed, `4` restore failed, `5` production-collision guard.
6. **Schedule it weekly** via Windows Task Scheduler so silent corruption is caught within 7 days.

### C. Real recovery (only when something is actually broken)
1. Open PowerShell at the project root.
2. Run, pointing at the backup you want:
   ```powershell
   scripts\restore-native.ps1 -BackupFile .\backups\wms-<timestamp>.dump.gpg
   ```
   By default it **refuses to overwrite an existing database**. Pass `-Force` to drop and recreate. The matching `-filestore.zip.gpg` next to the dump is auto-detected, decrypted, and extracted over the data dir.
3. The Admin can find the exact CLI command and the backup folder path from **WMS → Configuration → Restore from backup...** (an instructions page — restoring from a web upload is intentionally not a one-click action because it's destructive).

### D. Monitor health
1. From a monitor (or a browser/`curl`), request:
   ```
   GET /wms/health
   ```
2. The response is JSON: `{status, db_reachable, last_backup_age_hours, last_drill_age_days, warnings[]}`.
   - **status** is `HEALTHY`, `DEGRADED`, or `CRITICAL`.
   - HTTP **200** for HEALTHY/DEGRADED; HTTP **503** when not HEALTHY (i.e. CRITICAL).
3. Escalation logic:
   - **CRITICAL** — no successful database backup has ever been recorded (or the endpoint itself failed).
   - **DEGRADED** — the last backup is older than 24 hours, or there is no/older-than-7-days successful restore drill.
   - **HEALTHY** — a fresh backup and a recent drill.
4. Example CRITICAL warnings: `"no successful database backup on record"`, `"no successful restore drill on record"`. The fix for both is to run `scripts\backup-native.ps1` (and then the restore drill). A daily Odoo cron also escalates staleness into a warning row and pings Managers via Discuss.

### E. Read the Backup & DR Audit screen
1. Open **WMS → Reports → Backup & DR Audit** (Manager-only).
2. Read the columns: **Event Time**, **Audit Type** (Database backup / Filestore backup / Restore drill / Staleness warning), **Name** (the filename or drill label), **Success** (green/red toggle), **Verified**, and **Size Mb** (with a total). Rows are red when `Success = false`, green when true.
3. Use the search filters: **Failures only**, **Backups**, **Restore drills**, **Staleness warnings**, and group by Type or Outcome. The screen is append-only — you cannot create, edit, or delete rows here. As the screen's own note says: *"Rows here are written automatically by scripts/backup-native.ps1 and scripts/restore-drill.ps1 after each run."*

## Worked Example
A fresh install has never been backed up.

1. The monitor hits `/wms/health` and gets HTTP 503 with `{"status":"CRITICAL", "warnings":["no successful database backup on record","no successful restore drill on record"], ...}`.
2. The Admin opens PowerShell at the project root and runs `scripts\backup-native.ps1`. The console shows the dump, the encryption, `pg_restore --list OK (1843 TOC entries)`, the filestore zip, and retention. Two artifacts appear in `.\backups\`.
3. The Admin runs `scripts\restore-drill.ps1` (DryRun). It decrypts the new backup, verifies the TOC, and logs an OK drill.
4. The Admin opens **WMS → Reports → Backup & DR Audit** and sees three new green rows: a **Database backup** (Verified, ~size), a **Filestore backup**, and a **Restore drill** (Verified).
5. `/wms/health` now returns HTTP 200 `{"status":"HEALTHY", "last_backup_age_hours":0.1, "last_drill_age_days":0.0, "warnings":[]}`.

## Common Errors & What They Mean
- **"BACKUP_PASSPHRASE not set in .env."** — Add a strong 24+ char passphrase to `.env` and re-run.
- **"BACKUP_PASSPHRASE is still the placeholder 'changeme_backup_passphrase'."** — Replace the placeholder with a real random string.
- **"gpg.exe not found on PATH."** — Install Gpg4win (`winget install GnuPG.Gpg4win`) or add gpg to PATH.
- **"pg_dump failed. Set $env:PGPASSWORD if Postgres needs a password."** — Postgres rejected the connection; the password wasn't picked up from `odoo.native.conf`. Set `$env:PGPASSWORD` or fix the conf.
- **"Fresh dump has only N TOC entries - expected 1000+. Backup aborted."** / **"pg_restore --list rejected the fresh dump…"** — The dump looks truncated/corrupt; the backup is aborted on purpose so a bad backup is never kept. Investigate disk space / Postgres health and re-run.
- **Restore drill exit 2 / "gpg decrypt exit … Bad session key"** — The passphrase doesn't match what the backup was encrypted with (e.g. it was rotated). Use the passphrase that created that backup.
- **Restore drill exit 3 / "TOC has only N lines - expected 1000+…"** — The backup is truncated; treat it as unusable and rely on an earlier good backup.
- **"Refusing to act - drill DB name '…' does not match safety pattern."** — Internal safety guard; the drill will not run against anything that isn't a `wms_drill_<timestamp>` database. This protects production.
- **`restore-native.ps1` refuses to run** — By default it won't overwrite an existing database. Re-run with `-Force` only when you intend to drop and recreate.
- **No new rows on the Backup & DR Audit screen** — The script logs "backup audit not recorded (is wms_reports installed?)". The backup/drill still succeeded; install/upgrade `wms_reports` so audit writes land.

## Troubleshooting
- **Health says DEGRADED even though I just backed up.** DEGRADED can be driven by the *restore drill* being stale (>7 days) even when the backup is fresh. Run `scripts\restore-drill.ps1`.
- **Health says CRITICAL.** Either no successful DB backup exists yet (run the backup), or the endpoint failed internally (check the Odoo service is up — `db_reachable` is only true when Odoo answered).
- **The drill writes its row to the wrong database.** It targets the production DB via `-AuditDb` (default `wms`), because that's where Odoo reads. Pass `-AuditDb <name>` if your production DB isn't `wms`.
- **Backups are piling up / disk filling.** Lower `-Retain`, or move older `.gpg` files off-host. Retention deletes both the dump and its matching filestore zip.
- **I rotated the passphrase and old drills started failing.** Old backups are encrypted with the old passphrase. Keep the matching passphrase for any backup you still need to restore, and run a fresh backup with the new passphrase so new drills pass.
- **I want event-log alerts on Windows.** Register the source once as admin: `New-EventLog -LogName Application -Source 'WMS_Backup_Drill'`. Without it, the drill still writes its file log.

## Best Practices
- **Automate both.** Schedule `backup-native.ps1` (e.g. nightly) and `restore-drill.ps1` (weekly) in Task Scheduler. The 24h / 7-day health thresholds assume that cadence.
- **Store the passphrase off the server.** The `.gpg` files are useless without it; the server and the passphrase must not be lost together.
- **Keep backups off-host too.** Copy `.gpg` artifacts to separate storage so a single drive failure doesn't take the backups with the server.
- **Watch the Backup & DR Audit screen weekly.** Use the **Failures only** filter — any red row means a backup or drill failed and needs attention.
- **Poll `/wms/health` from a monitor.** Turn "are we protected?" into an automatic alert rather than a thing someone has to remember.
- **Do a full restore drill periodically** (`-DryRun:$false`), not just the TOC check, so you've proven an end-to-end recovery — and never against production.
- **Never weaken the safety guards.** The drill's production-collision check and `restore-native.ps1`'s overwrite refusal exist to prevent data loss.

## Related Help-Center Articles
- `what-is-a-backup`
- `what-is-a-restore-drill`
- `what-is-a-health-check`
- `workflow-backup-verification`
- `workflow-restore-drill`
- `admin-path-backups-and-restore-drill`
- `admin-path-observability-health`

## Narration Script
*(Target length ~4 minutes.)*

- **[0:00]** "In this video we'll protect the trust's data — backups, the weekly restore drill, health monitoring, and the in-app screen that proves it all ran. This is an Admin task, run from PowerShell on the server."
- **[0:18]** "The golden rule: a backup that has never been restored is not a backup. So we do two things — back up, and prove we can restore."
- **[0:32]** "First, the backup. Open PowerShell at the project root and run scripts, backslash, backup-native.ps1. It dumps the database, pipes it straight into G-P-G encryption so the plaintext barely touches disk, then verifies the dump with pg_restore list — if the table of contents is too small, it aborts, because a truncated backup is worse than none."
- **[1:05]** "It also zips and encrypts the filestore, applies retention to keep the last fourteen by default, and writes a row into the Backup and D-R Audit table. The encrypted files land in the backups folder, named with a timestamp."
- **[1:30]** "One thing to stress: everything is encrypted with the BACKUP_PASSPHRASE from your dot-env file. Without that passphrase the files can't be restored — so store it off the server."
- **[1:50]** "Next, the weekly restore drill. Run scripts, backslash, restore-drill.ps1. By default it does a cheap check — it decrypts the latest backup and verifies the table of contents, without creating any database. Add dash DryRun colon dollar-false for a full end-to-end test that restores into a throwaway database and then drops it. It refuses to touch anything that isn't a wms_drill database, so production is always safe."
- **[2:25]** "The drill logs its result into the same audit table. Schedule it weekly in Task Scheduler so any silent corruption is caught within seven days."
- **[2:45]** "Now monitoring. The system answers at slash wms slash health with a simple status: HEALTHY, DEGRADED, or CRITICAL. CRITICAL means no successful backup on record — and the fix is simply to run the backup script. DEGRADED means the backup is over a day old, or the drill is over a week old. A monitoring tool polls this and alerts someone automatically."
- **[3:15]** "Finally, the evidence. Open WMS, Reports, Backup and D-R Audit. Every backup and drill appears here automatically — event time, type, name, whether it succeeded, whether it was verified, and the size. Red rows are failures. You can't edit this screen; the scripts write it. Use the Failures-only filter for a quick weekly check."
- **[3:45]** "If you ever need a real recovery, run scripts, backslash, restore-native.ps1, pointing at the backup file — it refuses to overwrite a live database unless you pass dash Force."
- **[4:00]** "Automate both scripts, store the passphrase off-site, keep copies off-host, and watch the audit screen. Thank you."

## Recording Checklist
1. Open PowerShell at the project root.
2. Run `scripts\backup-native.ps1`; show the dump, encryption, `pg_restore --list OK`, filestore, and retention output.
3. Show the two new artifacts in `.\backups\`.
4. Run `scripts\restore-drill.ps1`; show the decrypt + TOC OK output.
5. (Optional) Run `scripts\restore-drill.ps1 -DryRun:$false`; show the drill DB created, probed, and dropped.
6. In a browser or `curl`, hit `/wms/health`; show the JSON status (HEALTHY) and HTTP 200.
7. (Optional) Show a CRITICAL/503 example before the first backup.
8. Log in to Odoo as a Manager; open **WMS → Reports → Backup & DR Audit**.
9. Point out Event Time, Audit Type, Name, Success, Verified, Size Mb; apply the **Failures only** filter.
10. Show **WMS → Configuration → Download encrypted backup** and **Restore from backup...** menu entries; end on the audit screen.

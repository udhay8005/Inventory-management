# Restore drill runbook

A backup that has never been restored is not a backup. This runbook describes
the weekly restore drill we use to prove the latest `backups\*.dump.gpg` file
is recoverable — without ever touching the production database.

## Why drill weekly

Three classes of silent corruption are caught only by an end-to-end restore:

1. **Truncated GPG envelope.** A backup that was killed mid-write may still
   produce a syntactically valid `.dump.gpg` file. `pg_restore --list` will
   reject it.
2. **Schema drift breaking pg_restore compatibility.** A module upgrade may
   introduce a column type that the dump's table-of-contents references but
   the destination cluster cannot reconstruct.
3. **GPG passphrase rot.** If `BACKUP_PASSPHRASE` in `.env` was rotated but
   the rotation was never tested, every backup since the rotation is
   unrecoverable.

A weekly drill catches all three within 7 days of the bug landing.

## What the drill does

`scripts\restore-drill.ps1` performs these steps in order:

1. Find the latest `*.dump.gpg` under `.\backups\` (or the file passed via
   `-BackupPath`).
2. Read `BACKUP_PASSPHRASE` from `.env`. Reject placeholders.
3. Locate `gpg.exe` (PATH probe, then Gpg4win install dirs).
4. Decrypt to a temp file (ACL = current user only, removed on exit).
5. Run `pg_restore --list` and count TOC entries. Expect 1000+.
6. **If -DryRun (default):** stop here. Cheap; runs in seconds.
7. **If -DryRun:$false:**
   - Create `wms_drill_<yyyyMMdd_HHmmss>` database. The name is enforced by
     a regex safety pattern — the script REFUSES to act if the resolved
     name does not match `^wms_drill_\d{8}_\d{6}$`.
   - `pg_restore --no-owner --no-privileges -d wms_drill_<ts> <decrypted>`.
   - Sanity probe: `SELECT count(*) FROM res_users` — every Odoo DB has it.
   - Drop the drill DB unless `-KeepDrillDb` is passed.
8. Cleanup: temp file removed in a `finally` block, even on exception.
9. Write a line to `.runtime\logs\restore-drill.log` (created on first drill
   run) and (best-effort) a Windows Application Event Log entry under source
   `WMS_Backup_Drill`.

## Prerequisites

Both are auto-handled on a standard install — listed here for clean recovery
hosts:

- **PostgreSQL client tools** (`psql`, `pg_restore`). The script auto-detects
  them from the `postgresql-x64` service / the `HKLM\SOFTWARE\PostgreSQL`
  registry keys / the standard `C:\Program Files\PostgreSQL\<ver>\bin` dirs
  (newest version first), so PostgreSQL's `bin\` does **not** need to be on
  PATH. If detection fails the drill exits **6** with a message naming
  everywhere it looked.
- **PostgreSQL authentication.** `psql`/`pg_restore` connect as the `db_user`
  from `config\odoo.native.conf`. The script reads `db_password` from that file
  into `PGPASSWORD` for the run (and clears it afterwards). If your conf has no
  `db_password`, set it yourself before running:
  ```powershell
  $env:PGPASSWORD = '<the odoo role password>'
  scripts\restore-drill.ps1
  ```
  A full restore (`-DryRun:$false`) also needs the role to have **CREATEDB**
  (the installer grants this to `odoo`; see the troubleshooting note below).

## Scheduling

### One-time setup as admin

The daily backup, the weekly restore drill, and the on-demand manual-backup
task are registered from source by a single idempotent script — re-running
it REPLACES the tasks, so a rebuilt host comes up with the exact same
schedule:

```powershell
# Register the Event Log source so the drill can write entries.
New-EventLog -LogName Application -Source 'WMS_Backup_Drill'

# Register "WMS Daily Backup", "WMS Weekly Restore Drill", and
# "WMS Manual Backup" (trigger-less; run by the Backup Now wizard) at once.
# Self-elevates via UAC; idempotent — safe to re-run after a host rebuild.
scripts\install-backup-tasks.ps1
```

The installer sets `Principal=NT AUTHORITY\SYSTEM`,
`LogonType=ServiceAccount`, `RunLevel=Highest`, with
`-StartWhenAvailable`, `ExecutionTimeLimit=2h`, and
`MultipleInstances=IgnoreNew`. Defaults are 4:30 PM daily for the backup
and 3:00 AM Sunday for the drill (override with `-BackupAt` / `-DrillAt`).

This pattern was introduced in v16.3 CR-1 — earlier versions used the
Interactive principal, which silently stopped firing when the console
session locked, leaving DR untested for weeks while the health endpoint
still reported HEALTHY. Running as SYSTEM ensures backups and drills
fire regardless of console state (locked, logged-off, headless box).

To remove the tasks (e.g. before decommissioning a host), use the
inverse:

```powershell
scripts\uninstall-backup-tasks.ps1
```

### Quarterly: run a full restore

The weekly drill is cheap (TOC-only). Once a quarter, run a full restore
to also verify pg_restore + the Odoo schema actually reconstruct:

```powershell
scripts\restore-drill.ps1 -DryRun:$false
```

The drill DB is named `wms_drill_<timestamp>` and dropped on exit.

## Interpreting results

| Exit code | Meaning | Action |
|---|---|---|
| 0 | Drill passed | Nothing — backups are recoverable. |
| 1 | Backup file missing | Check Task Scheduler — was the daily backup actually written? |
| 2 | Decrypt failed | Check `BACKUP_PASSPHRASE` in `.env`. Has it been rotated without testing? |
| 3 | TOC check failed | The `.dump.gpg` is likely truncated. Re-run `scripts\backup-native.ps1` to produce a fresh dump. |
| 4 | Restore into drill DB failed | Schema drift or pg_restore version mismatch. Check the PostgreSQL major version on the drill cluster matches the source. |
| 5 | Safety-pattern collision | Should never happen unless the script was modified. Revert. |
| 6 | PostgreSQL client tools missing | `psql`/`pg_restore` not found. Install PostgreSQL (15/16/17) or add its `bin\` to PATH. The message names the service / registry / install dirs it searched. |

## When a real restore is needed

This script is the DRILL. For a real recovery, use `scripts\restore-native.ps1`
which prompts for the passphrase explicitly and writes into the production
`wms` database. Read `docs/07-deployment.md` § Backup / Restore first.

## Troubleshooting

**"BACKUP_PASSPHRASE is still the placeholder"**
The drill refuses to proceed when `.env` has `BACKUP_PASSPHRASE=changeme_backup_passphrase`.
Replace it with the real passphrase from your password manager, then re-run.

**"gpg.exe not found"**
Install Gpg4win: `winget install GnuPG.Gpg4win`. Or set `-Passphrase` on
the CLI and ensure `gpg.exe` is on PATH for the user running the task.

**"Decrypted file suspiciously small"**
The threshold is 1 MB. A real WMS dump is at least a few MB. If the
decrypted file is smaller, the GPG envelope likely contained a truncated
pg_dump output. Re-run the backup.

**"TOC has only N lines — expected 1000+"**
The dump was probably interrupted. Re-run `scripts\backup-native.ps1` and
keep an eye on disk space + the backup-native.ps1 console output.

**"Could not create drill DB"**
The 'odoo' Postgres role needs CREATEDB. `scripts\install-native.ps1` sets
this; verify with: `psql -U postgres -c "\du odoo"`.

**Event Log entries missing**
The `WMS_Backup_Drill` source needs one-time registration as admin (see
"One-time setup" above). The drill silently skips Event Log writes if the
source is not registered; it still writes to the file log.

## Off-site backup

Drill verifies the LOCAL backup is recoverable. For real DR, the encrypted
`.dump.gpg` and `.zip.gpg` files must also live off-host.

**Built-in (recommended):** set `BACKUP_OFFSITE_DIR` in `.env` to any reachable
path — a USB drive, a UNC network share, or a OneDrive/Dropbox sync folder.
`scripts/backup-native.ps1` will automatically copy every encrypted artifact
there after the local backup completes, SHA-256-verify the copy against the
source, and record a `backup_offsite` audit row. No extra scheduler entry, no
extra credentials.

```ini
# .env
BACKUP_OFFSITE_DIR=C:\Users\<you>\OneDrive\wms-backups-offsite
# or: BACKUP_OFFSITE_DIR=\\nas\wms-backups
# or: BACKUP_OFFSITE_DIR=E:\wms-backups   # USB drive letter
```

**Built-in cloud tier (optional):** with Google Drive configured (see
[22-gdrive-backup.md](22-gdrive-backup.md)), every encrypted set is also
uploaded to the `Inventory_Backups` Drive folder after the local backup,
verified via Drive's `sha256Checksum`. To retrieve and verify a Drive copy:

```powershell
scripts\gdrive-restore.ps1 -List                                  # browse the Drive catalog
scripts\gdrive-restore.ps1 -SetStamp <yyyyMMdd-HHmmss>            # download + SHA-256 + GPG envelope verify
```

The download is renamed back to the local `wms-<stamp>.dump.gpg` naming, so
the drill command below works on it unchanged.

**Optional second-tier** (a redundant copy reaches a completely separate sync window):

- `rclone copy backups\ b2:wms-backups\` daily.
- OR `robocopy backups\ \\nas\wms-backups\ /MIR` daily.

Run the drill against the off-site copy at least monthly:

```powershell
scripts\restore-drill.ps1 -BackupPath D:\offsite-mount\wms-20260520-152106.dump.gpg
```

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
9. Write a line to `.runtime\logs\restore-drill.log` and (best-effort) a
   Windows Application Event Log entry under source `WMS_Backup_Drill`.

## Scheduling

### One-time setup as admin

```powershell
# Register the Event Log source so the drill can write entries.
New-EventLog -LogName Application -Source 'WMS_Backup_Drill'

# Register the weekly Task Scheduler entry.
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
              -Argument '-NoProfile -File "D:\Udhay\projects\Inventory_mngt\scripts\restore-drill.ps1"'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName 'WMS Restore Drill' `
                       -Action $action -Trigger $trigger -Settings $settings `
                       -RunLevel Highest
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
`.dump.gpg` and `.zip.gpg` files must also live off-host. Recommended:

- `rclone copy backups\ b2:wms-backups\` daily.
- OR `robocopy backups\ \\nas\wms-backups\ /MIR` daily.

Run the drill against the off-site copy at least monthly:

```powershell
scripts\restore-drill.ps1 -BackupPath D:\offsite-mount\wms-20260520-152106.dump.gpg
```

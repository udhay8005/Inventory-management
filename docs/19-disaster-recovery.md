# 19 — Disaster recovery runbook

A backup that has never been restored on a *new host* is only half-proven. This
runbook walks an Admin through rebuilding the WMS from scratch on a brand-new
Windows machine, using only the off-site encrypted backup pair and the project
source. The target round-trip is **~85 minutes** from "the old box is gone" to
"users can sign in on the new box".

The 18-restore-drill.md runbook proves the *local* `.dump.gpg` is recoverable
weekly. This runbook proves the *off-site* `.dump.gpg` is recoverable on a host
that has never seen this project before.

---

## 1. Scope and prerequisites

**Use this runbook when:** the production host is unrecoverable (disk failure,
ransomware, theft, hardware end-of-life) and you need to stand the WMS back up
on a different box.

**Do NOT use this runbook to:** migrate to a larger box (use
`scripts\backup-native.ps1` + `scripts\restore-native.ps1` on the same host
config), recover a single deleted record (Odoo's audit log + filestore are
sufficient), or test backups (use `scripts\restore-drill.ps1` — see
18-restore-drill.md).

**What you must have on hand**

| Asset | Where it lives | Notes |
|---|---|---|
| Off-site `<db>-<ts>.dump.gpg` | `BACKUP_OFFSITE_DIR` mirror (USB / NAS / OneDrive) | Encrypted Postgres dump |
| Off-site `<db>-<ts>-filestore.zip.gpg` | Same directory, same `<ts>` | Encrypted attachments/photos |
| `BACKUP_PASSPHRASE` | Password manager (NOT in `.env` on the dead host) | Required to decrypt both artifacts |
| `.env` values | Password manager / IT vault | At minimum `DB_PASSWORD`, `BACKUP_PASSPHRASE`, `ODOO_ADMIN_PASSWD`, `BACKUP_OFFSITE_DIR` |
| Git repo access | `https://github.com/udhay8005/Inventory-management.git` | Public; no credentials needed |
| Local Administrator account | New Windows 10/11 or Server 2022 box | Required for winget, services, scheduled tasks |

**What you do NOT need**

- Docker, WSL2, or any virtualisation. The WMS runs natively on Windows.
- Internet access beyond the initial winget bootstrap (PostgreSQL, Python 3.12,
  wkhtmltopdf, Odoo source). After install-native.ps1 finishes, the box can be
  air-gapped.
- A copy of the dead host's filesystem. The `.env` values, the source repo, and
  the two `.gpg` files are the only inputs.

---

## 2. Bootstrap the new machine (T+0 to T+15min)

### 2.1 Update Windows and open an Admin PowerShell

```powershell
# Apply pending updates BEFORE installing PostgreSQL — PG installer is sensitive
# to mid-install Windows reboots.
#
# NOTE: Get-WindowsUpdate is NOT a built-in Windows cmdlet — it ships in the
# PSWindowsUpdate gallery module. Install once per box:
#
#   # On a brand-new box you may first need to trust PSGallery:
#   Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
#   Install-Module -Name PSWindowsUpdate -Scope CurrentUser -Force
#       # PowerShellGet is available in PS 5.1 by default — no extra install.
#
# Built-in alternative for a fresh box (no module install required):
#   usoclient StartScan
#   # then drive Settings → Windows Update → Check for updates → Install all → reboot.
Get-WindowsUpdate -Install -AcceptAll -AutoReboot      # PSWindowsUpdate module
# Or open Settings → Windows Update → Check for updates → Install all → reboot.
```

Right-click PowerShell → **Run as administrator**. Confirm:

```powershell
whoami /groups | findstr /i "S-1-16-12288"             # High Mandatory Level
winget --version                                       # any version
```

### 2.2 Clone the repository

```powershell
mkdir D:\Udhay\projects -ErrorAction SilentlyContinue
cd D:\Udhay\projects
git clone https://github.com/udhay8005/Inventory-management.git Inventory_mngt
cd Inventory_mngt
```

No Git yet? `winget install Git.Git`, close/reopen PowerShell, retry.

### 2.3 Restore the environment file

```powershell
copy .env.example .env
notepad .env
```

Fill at minimum:

| Key | Source |
|---|---|
| `DB_PASSWORD` | Strong new value, OR the prior production value if you want to keep restore semantics identical |
| `BACKUP_PASSPHRASE` | **Must match the passphrase the `.gpg` files were encrypted with** — pull from password manager |
| `ODOO_ADMIN_PASSWD` | Strong new value (will be re-applied post-restore) |
| `BACKUP_OFFSITE_DIR` | New off-site path on the new host (USB, UNC, OneDrive sync folder) |

Save and close.

### 2.4 Run the one-shot installer

```powershell
scripts\install-native.ps1
```

This idempotently installs **PostgreSQL 15/16/17 (auto-detected; winget installs
17 by default)**, **Python 3.12**, and **wkhtmltopdf** via winget; clones Odoo
19 into `.odoo\`; creates the venv in `.venv\`; pip-installs Odoo's deps plus
`statsmodels, pandas, numpy, Pillow, reportlab`; creates the `wms` database;
writes `config\odoo.native.conf`; and runs Odoo's first-time init.

**Save the printed `wms_reports.health_token` value.** install-native.ps1
auto-generates a 32-hex token, writes it into the `ir.config_parameter` table,
and prints it to the console exactly once. Without it the /wms/health endpoint
returns 401. Store it next to `BACKUP_PASSPHRASE` in your password manager.

`✅ CHECKPOINT` — `Get-Service postgresql-x64-*` is Running, `Test-Path
.odoo\odoo-bin` is True, and you have the health_token in clipboard/manager.

---

## 3. Recover off-site artifacts (T+15 to T+25min)

### 3.1 Mount the off-site medium

- **USB drive:** plug in, note the drive letter (e.g. `E:`).
- **NAS / UNC share:** `net use Z: \\nas\wms-backups /persistent:no`
- **OneDrive / Dropbox:** sign in to the desktop client and let it finish the
  initial sync. Wait until the folder shows the green-check "Available on this
  device" state for both `.gpg` files.

### 3.2 Identify the latest pair

Both artifacts must share the **same `<ts>` timestamp** — the daily backup
writes them as a pair, and `scripts\restore-native.ps1` expects matched halves.

```powershell
$src = 'E:\wms-backups-offsite'        # adjust to your mounted path
Get-ChildItem $src -Filter '*.gpg' |
    Sort-Object LastWriteTime -Descending |
    Select-Object Name, Length, LastWriteTime -First 10
```

Expect to see two newest files with names like:

```
wms-20260607-163000.dump.gpg
wms-20260607-163000-filestore.zip.gpg
```

The shared `20260607-163000` is the timestamp pair. If only one half exists for
the newest timestamp, step back to the next-newest pair where both halves are
present.

### 3.3 Verify SHA-256 integrity

If the off-site location was written by `scripts\backup-native.ps1` (the
standard flow), a `.sha256` companion was also copied. Compare:

```powershell
$dump = Join-Path $src 'wms-20260607-163000.dump.gpg'
$sha  = Join-Path $src 'wms-20260607-163000.dump.gpg.sha256'
$expected = (Get-Content $sha).Split(' ')[0].Trim()
$actual   = (Get-FileHash $dump -Algorithm SHA256).Hash.ToLower()
if ($expected -eq $actual) { 'OK' } else { "MISMATCH expected=$expected actual=$actual" }
```

Repeat for the `-filestore.zip.gpg` half. Both must report `OK` before
continuing. A mismatch means the off-site medium corrupted the artifact in
transit — step back to the next-newest matched pair.

### 3.4 Resolve `$psql` for the rest of this runbook

Several later steps invoke `psql.exe` via a `$psql` variable. Resolve it once,
now, so § 4.4 / § 7.1 / § 7.2 / § 8.4 can use it without re-deriving the path.
The same auto-detection pattern is used in INSTALLATION-GUIDE.md Phase 3:

```powershell
$psql = (Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1).FullName
if (-not $psql) { throw 'psql.exe not found under C:\Program Files\PostgreSQL\*\bin\ — install-native.ps1 may not have completed.' }
$psql
```

Expect a path like `C:\Program Files\PostgreSQL\17\bin\psql.exe`. All later
uses invoke it with the call operator: `& $psql ...`.

### 3.5 Alternative: recover from Google Drive

If the dead host ran the Google Drive integration (see
[22-gdrive-backup.md](22-gdrive-backup.md)), the encrypted sets also live under
`Inventory_Backups/YYYY/MM-MonthName/YYYY-MM-DD/` in the operator's My Drive —
an alternative to §§ 3.1–3.3 when no other off-site medium survived. The token
file from the dead host is DPAPI machine-scope and useless off-box by design,
so re-consent on the new box, then download with built-in verification:

```powershell
# .env needs GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET (the same OAuth client as before)
scripts\setup-gdrive-auth.ps1                              # one-time browser consent
scripts\gdrive-restore.ps1 -List                           # browse Year > Month > Day
scripts\gdrive-restore.ps1 -SetStamp <yyyyMMdd-HHmmss>     # download-only (no -AutoRestore)
```

The download triple-verifies SHA-256 (file bytes vs `SHA256.txt` vs
`backup-info.json`), checks the GPG envelope, and renames the artifacts back to
the local `wms-<stamp>.dump.gpg` naming — § 4.3 then proceeds unchanged. (No
OAuth client at hand? The operator's Google account owns the files: download
them manually from drive.google.com and rename per `backup-info.json`'s
`local_name` map.)

---

## 4. Stop Odoo, run the restore (T+25 to T+45min)

### 4.1 Stop Odoo defensively

install-native.ps1 may have started a transient Odoo process during init.
Restore-native.ps1 will refuse to overwrite a database that has open
connections, so stop everything first:

```powershell
scripts\stop-native.ps1
Get-Service Odoo-WMS -ErrorAction SilentlyContinue   # not yet installed; OK if missing
```

### 4.2 Copy the artifacts local (optional but faster)

Restoring directly from a USB or OneDrive sync folder works, but copying to a
local SSD first avoids mid-restore I/O stalls on flaky media:

```powershell
mkdir backups -ErrorAction SilentlyContinue
copy "$src\wms-20260607-163000.dump.gpg"            backups\
copy "$src\wms-20260607-163000-filestore.zip.gpg"   backups\
```

### 4.3 Run the restore

```powershell
scripts\restore-native.ps1 -BackupFile backups\wms-20260607-163000.dump.gpg -Force
```

**`-Force` is mandatory on a fresh-box DR rebuild.** Step 2.4
(`install-native.ps1`) already created the `wms` database and seeded it (base
modules + the `wms_reports.health_token` row). Without `-Force`,
restore-native.ps1 hits its DB-exists guard and exits 1 with:

```
Database 'wms' already exists. Pass -Force to drop + restore.
```

With `-Force`, the script issues `DROP DATABASE wms;` against the `postgres`
maintenance DB, then `CREATE DATABASE wms OWNER odoo;`, and finally runs
`pg_restore` into the empty shell. The install-bootstrap DB is destroyed by
design — that is the whole point of restoring from off-site backup.

The script:

1. Reads `BACKUP_PASSPHRASE` from `.env`. Refuses to proceed on placeholders.
2. Decrypts via **GPG --symmetric --cipher-algo AES256, passphrase via
   short-lived `--passphrase-file` invoked through `cmd /c`** (avoids
   PowerShell 5.1 NativeCommandError on gpg-agent stderr).
3. Drops + recreates the `wms` database (owner `odoo`) — only because you
   passed `-Force`. Without `-Force`, the script exits 1 at this point.
4. Runs `pg_restore -U odoo -h <host> -p <port> -d wms --no-owner --no-acl
   <decrypted-dump>` and checks the exit code. **There is no `pg_restore
   --list` TOC sanity gate in this script** — that gate lives in
   `scripts\restore-drill.ps1` (the weekly drill), not in the production
   restore path. If you want a pre-flight TOC check on a critical DR restore,
   run `restore-drill.ps1` against the same `.dump.gpg` first.
5. Unzips the matching `-filestore.zip.gpg` half into `.runtime\filestore\wms\`.
   **There is no SHA-256 verification against `.sha256` companions in this
   script** — SHA-256 sidecars are written by `backup-native.ps1` at backup
   time, and are verified manually via the `Get-FileHash` block in § 3.3
   above. Do not skip § 3.3 expecting restore-native.ps1 to catch corruption.

### 4.4 Verify the restore landed

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "SELECT COUNT(*) FROM ir_module_module WHERE state='installed';"
```

Expect **≥ 7** — the seven WMS modules in install order are
`wms_location → wms_fifo → wms_barcode → wms_repair_damage →
wms_ai_forecast → wms_reports → wms_training`, plus whatever Odoo base
modules they pulled in. A count under 7 means the dump was incomplete; go
back to step 3.2 and pick the next-newest pair.

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "SELECT COUNT(*) FROM res_users WHERE active=true;"
```

Expect the same number of active users you remember from the dead host.

---

## 5. Re-register the service supervisor (T+45 to T+55min)

The dead host's Windows services and scheduled tasks are gone with the box.
Recreate them from source — both installers are idempotent.

### 5.1 Register the Odoo service

```powershell
scripts\install-odoo-service.ps1
Get-Service Odoo-WMS                # Status = Stopped (we'll start in step 6)
```

This creates the **`Odoo-WMS`** Windows service (NSSM-supervised) writing to
`.runtime\logs\odoo.log` (Odoo runtime) and `.runtime\logs\service-out.log` /
`.runtime\logs\service-err.log` (hyphen-separated NSSM stdout/stderr). Note:
`odoo-native.log` does NOT exist — if a guide mentions it, the guide is stale.

### 5.2 Register the backup + drill scheduled tasks

```powershell
# Register the Event Log source so the drill can write entries.
New-EventLog -LogName Application -Source 'WMS_Backup_Drill'

# Register "WMS Daily Backup", "WMS Weekly Restore Drill", and "WMS Manual Backup".
scripts\install-backup-tasks.ps1
```

This registers **"WMS Daily Backup"** (default 4:30 PM daily), **"WMS Weekly
Restore Drill"** (default 3:00 AM Sunday), and **"WMS Manual Backup"**
(trigger-less; run on demand by the in-app Backup Now wizard), all with
`Principal=NT AUTHORITY\SYSTEM`, `LogonType=ServiceAccount`,
`RunLevel=Highest`, `-StartWhenAvailable`, `ExecutionTimeLimit=2h`, and
`MultipleInstances=IgnoreNew`.

### 5.3 (Optional) Register the AI worker service

If the dead host ran the out-of-process forecasting worker:

```powershell
scripts\install-ai-worker-service.ps1
Get-Service Odoo-WMS-AIWorker
```

This creates the **`Odoo-WMS-AIWorker`** companion service.

### 5.4 Confirm BACKUP_OFFSITE_DIR is reachable by SYSTEM

The scheduled tasks run as `NT AUTHORITY\SYSTEM`, NOT as the interactive user.
A mapped drive letter from your logged-in session (e.g. `Z:\wms-backups`) is
invisible to SYSTEM. Use a UNC path, a local drive letter, or a path under
`C:\ProgramData\` that SYSTEM can write to.

```powershell
# Run a one-shot probe as SYSTEM:
$dest = (Get-Content .env | Select-String '^BACKUP_OFFSITE_DIR=' | ForEach-Object {
    ($_ -split '=',2)[1].Trim()
})
psexec -s -nobanner cmd /c "if exist `"$dest`" (echo SYSTEM-CAN-READ) else (echo NOT-REACHABLE)"
```

**`psexec` is a Sysinternals utility — not bundled with Windows.** Grab it from
the Microsoft Sysinternals Suite at
https://learn.microsoft.com/sysinternals/downloads/psexec, or install via
`winget install Microsoft.Sysinternals.PSTools`.

Or simpler — let step 7.2 below run the **"WMS Daily Backup"** task manually
(right-click → Run in Task Scheduler) and inspect the **Last Run Result**
column plus the `wms_backup_audit` row to confirm SYSTEM can reach
`BACKUP_OFFSITE_DIR`. That avoids needing psexec at all.

**If `BACKUP_OFFSITE_DIR` is blank in `.env`, off-site copy is disabled and
the local backup still succeeds.** That is a recoverable state; tighten it
later. If it is *set* but unreachable by SYSTEM, the off-site copy is
**failure-safe** — it errors out without failing the local backup, and writes
a warning row to `wms_backup_audit`.

---

## 6. Smoke-test the rebuilt site (T+55 to T+70min)

### 6.1 Start Odoo

```powershell
Start-Service Odoo-WMS
Get-Service Odoo-WMS                # Status = Running

# Tail the runtime log until "Registry loaded" appears (usually < 30s):
Get-Content .runtime\logs\odoo.log -Tail 40 -Wait
```

### 6.2 Hit the health gate

The /wms/health route is `auth='public'` but gated by the
`wms_reports.health_token` `ir.config_parameter` (auto-generated 32-hex by
install-native.ps1). Token comparison uses `odoo.tools.consteq`. Accepted as
`?token=<v>` query parameter OR `X-Health-Token` header.

```powershell
$token = '<the 32-hex token printed by install-native.ps1>'

# Happy path: 200, body { status, db_reachable, backup_file_present,
# last_backup_age_hours, last_drill_age_days, warnings }
curl.exe "http://localhost:8069/wms/health?token=$token"

# Negative path: 401, body {"status":"unauthorized"}
curl.exe "http://localhost:8069/wms/health"
```

Possible responses:

| Code | Body status | Meaning |
|---|---|---|
| 200 | `OK` / `WARN` | Healthy or recoverable (warnings array explains) |
| 401 | `unauthorized` | Missing or wrong token |
| 503 | `CRITICAL` | DB unreachable / backups stale / drill stale |
| 503 | `CRITICAL` + `detail: health check failed` | Internal exception during health gather |

Right after restore, expect `last_backup_age_hours` to read as the age of the
*restored* backup pair — this is correct; step 7.2 will produce a fresh entry.

### 6.3 Sign in

Browse to `http://localhost:8069/`, sign in with `admin` and the
`ODOO_ADMIN_PASSWD` you set in `.env`. Verify:

- **WMS** top-level Odoo app menu (seq=10) is visible.
- **WMS → Operations → Slots** lists your restored slots.
- **WMS → Operations → Damages** is a **single leaf** (no "Damages → New"
  child — that is intentional, the form opens directly).
- **WMS → Reports → Dashboard** renders without errors.
- **Help & Training** is its own **top-level Odoo app menu** (seq=6), NOT a
  submenu under WMS, with children **Getting Started** and **Help Center**.
  Help & Training (seq=6) renders before WMS (seq=10) in the app bar so new
  users land on training first — this ordering is intentional, not a typo.
- **WMS → Forecast / Reorder → Forecasts** renders (statsmodels is venv-pinned;
  if this 500s the venv install is incomplete — re-run install-native.ps1).

`✅ CHECKPOINT` — happy-path /wms/health is 200, negative-path is 401, you
can sign in, and Operations + Reports menus render.

---

## 7. Trigger one drill (T+70 to T+85min)

A scheduled task on a new box only fires at its next scheduled tick. Manually
trigger both tasks to prove they work on this box *today*.

### 7.1 Manually run the restore drill

Open `taskschd.msc` → Task Scheduler Library → right-click **"WMS Weekly
Restore Drill"** → **Run**.

Then tail the runtime log and the drill log:

```powershell
Get-Content .runtime\logs\odoo.log -Tail 40 -Wait
# In a second pane:
Get-Content .runtime\logs\restore-drill.log -Tail 20 -Wait
```

Expect `EXIT_OK` in the drill log. Then confirm an audit row landed:

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "SELECT audit_type, status, ts FROM wms_backup_audit ORDER BY ts DESC LIMIT 5;"
```

The newest row should have `audit_type='restore_drill'` and `status='OK'`.

### 7.2 Manually run the daily backup

Same place: right-click **"WMS Daily Backup"** → **Run**.

```powershell
Get-ChildItem backups\*.gpg | Sort-Object LastWriteTime -Descending | Select-Object -First 4
```

Two new `.gpg` files (and their `.sha256` companions) should appear with a
fresh timestamp. If `BACKUP_OFFSITE_DIR` is set, the same files should also
appear at that path within seconds.

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "SELECT audit_type, status, ts FROM wms_backup_audit WHERE audit_type IN ('backup','backup_offsite') ORDER BY ts DESC LIMIT 4;"
```

Expect a `backup` row with `status='OK'`. If `BACKUP_OFFSITE_DIR` is set,
expect a `backup_offsite` row too. A `backup_offsite` row with
`status='WARN'` means SYSTEM cannot reach the off-site path — see § 5.4.

`✅ CHECKPOINT` — both tasks fired manually, both wrote audit rows, off-site
mirror has a fresh pair.

---

## 8. Post-restore hardening

### 8.1 Rotate user passwords

The restored `res_users` table carries the dead host's password hashes. Anyone
who knew a user's old password still does. Force a rotation:

```powershell
scripts\set-user-passwords.ps1
```

The script writes strong randoms, displays them once, and writes nothing to
disk. Distribute to users via your usual channel (1Password, etc).

### 8.2 Confirm the placeholder deny-list rejects defaults

`.env` placeholders like `changeme_db_password` and
`changeme_backup_passphrase` are explicitly rejected by
`install-native.ps1`, `backup-native.ps1`, `restore-native.ps1`, and
`restore-drill.ps1`. Confirm none survived the bootstrap:

```powershell
Select-String .env -Pattern '^(DB_PASSWORD|BACKUP_PASSPHRASE|ODOO_ADMIN_PASSWD)='
# None of the values should be "changeme_*" or the .env.example default.
```

### 8.3 Confirm Odoo is locked down

```powershell
Select-String config\odoo.native.conf -Pattern '^(list_db|db_listing|without_demo|admin_passwd)\s*='
```

Required values:

```ini
list_db = False
db_listing = False
without_demo = True
admin_passwd = <the strong value you set in .env>
```

If any of `list_db` / `db_listing` are `True`, edit the file, save, and
`Restart-Service Odoo-WMS`. Leaving them `True` exposes the database manager
page at `/web/database/manager` — a known foot-gun on internet-reachable hosts.

### 8.4 Re-verify the named role model

The restored DB carries 3 named base roles plus capability sub-groups. Confirm
they survived:

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "
SELECT g.name AS role, COUNT(u.user_id) AS members
FROM res_groups g
LEFT JOIN res_groups_users_rel u ON u.gid = g.id
WHERE g.name IN ('group_wms_user','group_wms_manager','group_repair_tech','group_buyer',
                 'group_wms_can_scan_receive','group_wms_can_scan_issue','group_wms_can_file_damage',
                 'group_wms_can_submit_audit','group_wms_can_manage_catalog')
GROUP BY g.name ORDER BY g.name;"
```

You should see the 3 named base roles (`group_wms_user` = WMS / Store Keeper,
`group_wms_manager` = WMS / Manager, `group_repair_tech` = WMS / Repair Tech),
the optional `group_buyer` if used, and the 5 capability sub-groups (all in
the `wms_location` namespace).

---

## 9. Troubleshooting

**"`BACKUP_PASSPHRASE is still the placeholder`"**
You forgot to fill it in step 2.3, or pasted the placeholder verbatim. Edit
`.env`, paste the real value from your password manager, retry.

**`restore-native.ps1` aborts with `Database 'wms' already exists. Pass
-Force to drop + restore.`**
This is the single most likely DR failure on a fresh-box rebuild. Step 2.4
(`install-native.ps1`) inherently creates and seeds the `wms` database as
part of bootstrap, so by the time you reach § 4.3 the target DB already
exists. The restore-native.ps1 DB-exists guard then refuses to overwrite it
unless you pass `-Force`. Re-run the § 4.3 command with `-Force` appended:

```powershell
scripts\restore-native.ps1 -BackupFile backups\wms-20260607-163000.dump.gpg -Force
```

`-Force` will `DROP DATABASE wms;` (destroying the install-bootstrap shell)
and `CREATE DATABASE wms OWNER odoo;` before pg_restore runs. That is the
intended DR flow — the install-bootstrap DB is throwaway scaffolding for the
restore. Do NOT manually `DROP DATABASE wms;` first and re-run without
`-Force`; restore-native.ps1 expects to own the drop/create itself.

**GPG passphrase failures during restore (`gpg: decryption failed: Bad
session key`)**
The passphrase in `.env` does not match the one that encrypted the `.gpg`
files. This is the single most common DR failure. Confirm the value with
whoever rotated `BACKUP_PASSPHRASE` last. There is no recovery path other
than the correct passphrase — by design.

**`/wms/health` returns 401 with `{"status":"unauthorized"}` even with a
token**
Token mismatch. The token printed by `install-native.ps1` on the new box does
NOT match any token from the dead host — it was freshly generated. Always
read the token from this host:

```powershell
& $psql -U odoo -h localhost -p 5432 -d wms -c "SELECT value FROM ir_config_parameter WHERE key='wms_reports.health_token';"
```

**`backup_offsite` audit row reports `status='WARN'`**
SYSTEM cannot reach the path in `BACKUP_OFFSITE_DIR`. Common causes:
mapped-drive letter only visible to your interactive session; UNC path
requires credentials SYSTEM does not have; OneDrive sync folder is per-user.
Fix by using a UNC path SYSTEM can read, a local-drive path, or a path
under `C:\ProgramData\`. The local backup is unaffected — only the off-site
mirror is skipped.

**`Odoo-WMS` service refuses to start**
Read `.runtime\logs\service-err.log` for the NSSM-captured stderr, and
`.runtime\logs\odoo.log` for Odoo's own startup trace. Common causes:
`config\odoo.native.conf` `db_password` does not match the password the
`odoo` Postgres role was created with (re-run `install-native.ps1` to
reconcile); port 8069 is in use by another process
(`Get-NetTCPConnection -LocalPort 8069`); `.venv\` is corrupt
(`install-native.ps1 -Reset`).

**"Scheduled tasks fire but the runtime log is silent"**
Confirm the task is running as `NT AUTHORITY\SYSTEM` (Task Scheduler →
properties → Security options). The v16.3 CR-1 hardening moved both tasks
from `Interactive` to `SYSTEM` — Interactive principals silently stop firing
when the console session locks, leaving DR untested for weeks while the
health endpoint still reports HEALTHY.

---

## 10. References

- `scripts\install-native.ps1` — one-shot bootstrap (PG, Python, venv, DB, config, health_token).
- `scripts\restore-native.ps1` — production restore (this runbook § 4).
- `scripts\install-odoo-service.ps1` — Odoo-WMS service registration (§ 5.1).
- `scripts\install-backup-tasks.ps1` — Daily Backup + Weekly Restore Drill + Manual Backup registration (§ 5.2).
- `scripts\install-ai-worker-service.ps1` — optional Odoo-WMS-AIWorker service (§ 5.3).
- `scripts\set-user-passwords.ps1` — post-restore rotation (§ 8.1).
- [docs/INSTALLATION-GUIDE.md](INSTALLATION-GUIDE.md) — first-time install on a healthy box (longer-form than § 2 here).
- [docs/18-restore-drill.md](18-restore-drill.md) — weekly drill that proves the *local* `.dump.gpg` is recoverable.
- [docs/07-deployment.md](07-deployment.md) — overall deployment shape (native Windows, no Docker).
- [SECURITY.md](../SECURITY.md) — placeholder deny-list, locked-down Odoo flags, role model.

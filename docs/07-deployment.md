# 07 — Deployment

The WMS runs natively on Windows — no Docker, no virtualisation. PostgreSQL
runs as a Windows service; Odoo runs in a Python venv. The same layout works
on Linux (apt-installed Postgres + a venv) with one Makefile target.

## First-time bring-up (Windows)

```powershell
# From Administrator PowerShell:
git clone https://github.com/udhay8005/Inventory-management.git
cd Inventory-management
copy .env.example .env
# Edit .env: set DB_PASSWORD to something strong.

scripts\install-native.ps1
```

The installer:

1. Installs **PostgreSQL 15/16/17** (auto-detected; winget installs 17 by default), **Python 3.12**, **wkhtmltopdf**, **Git** via winget (skips any that are already present)
2. Creates the `odoo` Postgres role with `CREATEDB` + the password from `.env`
3. Creates the `wms` database
4. Clones Odoo 19.0 source into `.odoo\`
5. Creates a Python venv at `.venv\` and installs Odoo's deps + this project's extras
6. Generates `config\odoo.native.conf` keyed for the local Postgres
7. Runs Odoo's first-time DB init (`-i base --without-demo=all --stop-after-init`)

Then start the server:

```powershell
scripts\start-native.ps1
```

…and install the WMS modules in **Apps → Update Apps List → search "wms"**:

1. `wms_location`
2. `wms_fifo`
3. `wms_barcode`
4. `wms_repair_damage`
5. `wms_ai_forecast`
6. `wms_reports`
7. `wms_training`

## First-time bring-up (Linux / macOS)

```bash
# Install PostgreSQL 15/16/17 (auto-detected; winget installs 17 by default) + Python 3.12 via your package manager first.
sudo apt-get install -y postgresql-16 postgresql-client python3.12 python3.12-venv \
                        wkhtmltopdf libldap2-dev libsasl2-dev git

# Create the odoo role + db (one-time):
sudo -u postgres psql <<EOF
CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD '$(grep DB_PASSWORD .env | cut -d= -f2)';
CREATE DATABASE wms OWNER odoo;
EOF

make install            # clone Odoo, make venv, pip install
make start              # run odoo
```

## Day-2 ops

```powershell
# Logs (tail-follow)
Get-Content .runtime\logs\odoo.log -Wait

# Restart Odoo with a module upgrade
scripts\stop-native.ps1
scripts\start-native.ps1 -Upgrade wms_repair_damage

# psql
psql -U odoo -h localhost -d wms

# Odoo Python shell
.venv\Scripts\python .odoo\odoo-bin shell -c config\odoo.native.conf -d wms --no-http
```

## Backups

```powershell
scripts\backup-native.ps1
```

Writes timestamped artifacts to `.\backups\`:

- `wms-<timestamp>.dump.gpg` — `pg_dump` custom format, encrypted with `BACKUP_PASSPHRASE` from `.env` (the plaintext `.dump` is piped through GPG and never persisted)
- `wms-<timestamp>-filestore.zip.gpg` — the `data_dir\filestore\wms` tree, GPG-encrypted
- `wms-<timestamp>.dump.gpg.sha256` + `wms-<timestamp>-filestore.zip.gpg.sha256` — SHA-256 sidecars written at the same time, used to detect bit-rot and to gate restores

**Hardening (canonical):**

- GPG is invoked as `--symmetric --cipher-algo AES256` via `cmd /c` — the `cmd` shim is deliberate so PS 5.1 doesn't wrap gpg-agent's stderr into a `NativeCommandError` (each stderr line becomes an `ErrorRecord` and `$?` flips to `$false` even on exit 0)
- SHA-256 sidecars are written by `backup-native.ps1` at artifact-write time; verify manually at restore time, and the weekly drill auto-verifies them before decrypt
- `BACKUP_OFFSITE_DIR` is read from `.env` — blank = disabled; when set, each artifact (plus its `.sha256` sidecar) is mirrored to that path with the same 14-backup retention. Copy failures are logged but never abort the primary backup (failure-safe). The path must be reachable by `NT AUTHORITY\SYSTEM` (UNC paths need a machine-account ACL, not a user one)
- `/wms/health` is gated by the `wms_reports.health_token` `ir.config_parameter` (32-hex, auto-generated at install) using `consteq` — pass as `?token=` or the `X-Health-Token` header. See [08-security.md](08-security.md) for the full gate semantics

Default retention is 14 backups; pass `-Retain 30` for longer.

Schedule via **Windows Task Scheduler**:

```powershell
# One-line setup — registers both scheduled tasks as NT AUTHORITY\SYSTEM:
scripts\install-backup-tasks.ps1
```

This registers:

- **WMS Daily Backup** — runs `backup-native.ps1` daily at 1:00 PM
- **WMS Weekly Restore Drill** — runs `restore-drill.ps1` every Sunday at 3:00 AM

Both run as `NT AUTHORITY\SYSTEM` (LogonType=ServiceAccount, RunLevel=Highest, StartWhenAvailable, ExecutionTimeLimit=2h, MultipleInstances=IgnoreNew). See [docs/18-restore-drill.md](18-restore-drill.md) for the weekly drill runbook (scheduling, exit codes, troubleshooting).

### Restore

> **Note:** Backups are encrypted with `BACKUP_PASSPHRASE` from `.env`. Losing
> the passphrase = losing the backups. Store the passphrase OFF the server.

```powershell
# Create an empty database first
dropdb -U odoo -h localhost --if-exists wms_restore
createdb -U odoo -h localhost wms_restore

# Two-step encrypted restore: decrypts the .dump.gpg then runs pg_restore,
# and expands the matching filestore archive.
scripts\restore-native.ps1 `
    -DumpFile .\backups\wms-20260520-091500.dump.gpg `
    -TargetDb wms_restore
```

Then start Odoo against `wms_restore` to verify before swapping over.

### Restore drill

A weekly drill verifies the latest backup is recoverable WITHOUT touching the production database. The drill auto-verifies the `.sha256` sidecars, decrypts the most recent `.dump.gpg`, runs `pg_restore --list` against it with a **TOC ≥ 100 entries** sanity gate (failures abort), and (optionally) restores into a throwaway `wms_drill_<timestamp>` database which is dropped on exit. Note: the TOC gate lives in `restore-drill.ps1` only — `restore-native.ps1` is for human-driven restores and does not enforce it.

```powershell
# Cheap weekly check (TOC verification only):
scripts\restore-drill.ps1

# Quarterly: full restore into a drill DB:
scripts\restore-drill.ps1 -DryRun:$false
```

See [docs/18-restore-drill.md](18-restore-drill.md) for the full runbook (scheduling, exit codes, troubleshooting).

## Running Odoo as a Windows service

For production, you'll want Odoo to auto-start on boot and recover from
crashes. Two options:

### Option A — NSSM (recommended)

[NSSM](https://nssm.cc/download) wraps any executable as a Windows service. The canonical installer takes care of the wiring:

```powershell
# After scripts\install-native.ps1 completes:
scripts\install-odoo-service.ps1
```

This creates the **Odoo-WMS** service:

- Depends on the `postgresql-x64-*` service (auto-detected)
- Auto-starts on boot, restarts on failure
- Waits for `/wms/health` to return 200 before reporting healthy
- Logs stdout/stderr to `.runtime\logs\service-out.log` and `.runtime\logs\service-err.log`

If you have an AI-worker companion, install it too:

```powershell
scripts\install-ai-worker-service.ps1   # creates Odoo-WMS-AIWorker
```

**Manual fallback** (only if `install-odoo-service.ps1` is unavailable):

```powershell
nssm install Odoo-WMS `
    "D:\path\to\Inventory_mngt\.venv\Scripts\python.exe" `
    "D:\path\to\Inventory_mngt\.odoo\odoo-bin" `
    "-c" "D:\path\to\Inventory_mngt\config\odoo.native.conf" `
    "-d" "wms"

nssm set Odoo-WMS AppDirectory "D:\path\to\Inventory_mngt"
nssm set Odoo-WMS Start SERVICE_AUTO_START
nssm set Odoo-WMS AppStdout "D:\path\to\Inventory_mngt\.runtime\logs\service-out.log"
nssm set Odoo-WMS AppStderr "D:\path\to\Inventory_mngt\.runtime\logs\service-err.log"
Start-Service Odoo-WMS
```

### Option B — Task Scheduler (no extra binary)

Create a task that runs on system startup, executes `scripts\start-native.ps1`,
restart on failure, no user logon needed.

## HTTPS / production reverse proxy

Put nginx or Caddy in front. Example Caddyfile:

```
wms.example.org {
    reverse_proxy /websocket localhost:8069 {
        header_up Connection {>Connection}
        header_up Upgrade {>Upgrade}
    }
    reverse_proxy localhost:8069
}
```

Then set `proxy_mode = True` in `config\odoo.native.conf` so Odoo trusts the
forwarded headers. WebSocket and HTTP share port 8069 (single-process server)
so one upstream is enough.

## Optional thermal printer

Any thermal printer the host OS can see. The Odoo report engine generates the
PDF; the user's browser downloads it and sends it to the OS printer dialog.
Tested with 4×1 inch direct-thermal labels; layout is admin-configurable.

## Mobile / off-site access

The simplest local path:

```powershell
# Right-click PowerShell → Run as Administrator:
New-NetFirewallRule -DisplayName "WMS Odoo" -Direction Inbound -LocalPort 8069 -Protocol TCP -Action Allow
```

Phones on the same WiFi can then open `http://<host-IP>:8069`.

For internet access, run a [Cloudflare named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
via `cloudflared.exe` pointing at `localhost:8069`. Get a permanent HTTPS URL
on your own domain — see [12-mobile-access.md](12-mobile-access.md).

## Upgrades

```powershell
# Pull the latest WMS code
git pull origin main

# Upgrade affected modules without losing data
scripts\start-native.ps1 -Upgrade wms_location,wms_barcode,wms_repair_damage
```

For an Odoo minor-version upgrade (19.0 → 19.x stable updates):

```powershell
cd .odoo
git pull origin 19.0
cd ..
.venv\Scripts\pip install -r .odoo\requirements.txt --upgrade
scripts\start-native.ps1 -Upgrade all
```

Always run a backup first.

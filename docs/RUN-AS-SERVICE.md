# Run Odoo as a Windows Service

Make the WMS run itself — **start automatically on boot** and **restart automatically on failure** — instead of being launched by hand. This closes the gap where the app stops if the machine reboots or the launching session ends.

## Install (one time)

From the project folder, in PowerShell:

```powershell
.\scripts\install-odoo-service.ps1
```

- If you are not already in an elevated shell, it **relaunches itself as Administrator** — approve the single **UAC** prompt.
- If `nssm` (the service supervisor) is missing, it is installed automatically via `winget`.
- It stops any hand-started Odoo on port 8069, creates the service, starts it, and waits for `/wms/health` to report `HEALTHY`.

That's it. The service is named **`Odoo-WMS`**.

## What it sets up

| Property | Value |
| --- | --- |
| Start type | **Automatic** (starts on boot) |
| Supervisor | **NSSM** — restarts Odoo on any exit (5s delay, crash-loop throttle) |
| Extra safety net | Windows **recovery actions** (`sc.exe failure`) — restart on service crash |
| Runs after | the **PostgreSQL** service (dependency), so the DB is ready first |
| Account | **LocalSystem** (no stored password; DB auth uses the config password) |
| Boot path | reuses `scripts\start-native.ps1` (same env: PostgreSQL, wkhtmltopdf, pg_dump) |
| Logs | `.runtime\logs\service-out.log` / `service-err.log` (rotated at 10 MB) |

## Manage it

```powershell
Start-Service   Odoo-WMS      # start
Stop-Service    Odoo-WMS      # stop
Restart-Service Odoo-WMS      # restart
Get-Service     Odoo-WMS      # status
```

Or use the GUI: **`services.msc`** → *Odoo WMS (wms)*. The **Recovery** tab shows the failure/restart actions.

Live logs:
```powershell
Get-Content .\.runtime\logs\service-out.log -Tail 50 -Wait
```

## Verify after a reboot

```powershell
Get-Service Odoo-WMS                                   # should be Running
Invoke-WebRequest http://localhost:8069/wms/health     # should be HTTP 200 HEALTHY
```

## Uninstall

```powershell
.\scripts\uninstall-odoo-service.ps1
```

Removes the service (elevates via UAC). Odoo can still be started manually with `start-native.ps1` afterward.

## Notes

- **Upgrades / module changes:** stop the service, run `start-native.ps1 -Upgrade "<modules>"` once manually, then start the service again — so you can watch the upgrade output.
- The service and a manual `start-native.ps1` both bind port 8069 — run only one at a time.
- The daily **`WMS Daily Backup`** scheduled task is independent and keeps running regardless.

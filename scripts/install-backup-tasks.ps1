#Requires -Version 5.1
<#
.SYNOPSIS
    Register the WMS scheduled tasks - daily encrypted backup, weekly restore
    drill + on-demand manual backup - reproducibly and idempotently
    (Critical #7).

.DESCRIPTION
    Previously the daily backup was a hand-made Task Scheduler entry that did
    not survive a host rebuild. This script creates the tasks from source so
    a rebuilt machine restores the exact schedule:

      * "WMS Daily Backup"         - daily (default 16:30) -> backup-native.ps1
                                     (encrypted DB + filestore, retention, audit)
      * "WMS Weekly Restore Drill" - Sundays (default 03:00) -> restore-drill.ps1
                                     (decrypt + structural verify of the latest
                                     backup; never touches production)
      * "WMS Manual Backup"        - NO trigger -> backup-native.ps1 -Source manual
                                     (fired on demand by the WMS Backup Now screen
                                     or schtasks /Run; same SYSTEM pipeline as the
                                     daily task)
      * "WMS Pending Upload Sweep" - NO trigger -> backup-native.ps1 -PendingSweep
                                     (fired on demand by the hourly Odoo reconnect
                                     cron + the DR-page Retry Now button; re-uploads
                                     queued Drive sets without a fresh dump)

    Tasks run as the current user when logged on, with missed-run catch-up
    (StartWhenAvailable). Re-running REPLACES the tasks (idempotent).

    Needs Administrator rights; relaunches itself elevated if necessary.

.PARAMETER BackupAt
    Daily backup time. Default "4:30PM".

.PARAMETER DrillAt
    Weekly drill time (Sunday). Default "3:00AM".

.EXAMPLE
    .\scripts\install-backup-tasks.ps1
#>
[CmdletBinding()]
param(
    [string]$BackupAt = "4:30PM",
    [string]$DrillAt = "3:00AM"
)
$ErrorActionPreference = "Stop"

# --- self-elevate ---------------------------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $PSCommandPath),
        "-BackupAt", $BackupAt, "-DrillAt", $DrillAt
    )
    return
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$backupScript = Join-Path $ProjectRoot "scripts\backup-native.ps1"
$drillScript = Join-Path $ProjectRoot "scripts\restore-drill.ps1"
foreach ($p in @($backupScript, $drillScript)) {
    if (-not (Test-Path $p)) { throw "Missing required script: $p" }
}

# FPAT Critical: run the backup + drill as SYSTEM so they fire even when no
# user is logged on (locked console, after reboot, headless box). The previous
# Interactive principal silently stopped the moment the console locked, which
# meant DR could die for weeks with the health endpoint still saying HEALTHY.
# SYSTEM has the rights pg_dump and the script tree need; the runtime path
# already accepts non-interactive invocations.
$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" `
    -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

# --- Daily backup ---------------------------------------------------------
$backupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Source auto' -f $backupScript) `
    -WorkingDirectory $ProjectRoot
Register-ScheduledTask -TaskName "WMS Daily Backup" -Action $backupAction `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $BackupAt) `
    -Settings $settings -Principal $principal `
    -Description "Daily encrypted WMS DB + filestore backup (backup-native.ps1). Missed runs catch up when the PC next comes online." `
    -Force | Out-Null
Write-Host "Registered 'WMS Daily Backup' (daily $BackupAt)" -ForegroundColor Green

# --- Weekly restore drill -------------------------------------------------
$drillAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $drillScript) `
    -WorkingDirectory $ProjectRoot
Register-ScheduledTask -TaskName "WMS Weekly Restore Drill" -Action $drillAction `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $DrillAt) `
    -Settings $settings -Principal $principal `
    -Description "Weekly DR drill: verifies the latest encrypted backup is decryptable + structurally restorable (restore-drill.ps1). Never touches production." `
    -Force | Out-Null
Write-Host "Registered 'WMS Weekly Restore Drill' (Sundays $DrillAt)" -ForegroundColor Green

# --- Manual backup (on-demand) ---------------------------------------------
# Deliberately NO trigger: fired exclusively via schtasks /Run (the WMS
# Backup Now wizard, or an operator console). Same SYSTEM principal/settings
# as the daily task, so there is no env/permission drift between scheduled
# and on-demand backups; MultipleInstances IgnoreNew makes double-clicks
# harmless.
$manualAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Source manual' -f $backupScript) `
    -WorkingDirectory $ProjectRoot
Register-ScheduledTask -TaskName "WMS Manual Backup" -Action $manualAction `
    -Settings $settings -Principal $principal `
    -Description "On-demand backup triggered from the WMS Backup Now screen (or schtasks /run). Same pipeline as the daily task." `
    -Force | Out-Null
Write-Host "Registered 'WMS Manual Backup' (on-demand, no schedule)" -ForegroundColor Green

# --- Pending upload sweep (on-demand) --------------------------------------
# v18 offline queue: trigger-less SYSTEM task fired via schtasks /Run by the
# hourly Odoo reconnect cron (_cron_retry_gdrive_uploads) and the DR-page
# "Retry Now" button. Runs backup-native.ps1 -PendingSweep, which re-uploads
# already-encrypted pending sets (Stage 5a + quota cache) WITHOUT taking a
# fresh dump - so it never touches the local backup or the Backup Now poll
# watermark. Same SYSTEM principal/settings as the other tasks (no drift);
# MultipleInstances IgnoreNew makes overlapping cron+button fires harmless.
$sweepAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -PendingSweep' -f $backupScript) `
    -WorkingDirectory $ProjectRoot
Register-ScheduledTask -TaskName "WMS Pending Upload Sweep" -Action $sweepAction `
    -Settings $settings -Principal $principal `
    -Description "On-demand Google Drive pending-upload sweep (backup-native.ps1 -PendingSweep). Re-uploads queued backup sets when connectivity returns; no fresh dump. Fired by the hourly reconnect cron and the DR-page Retry Now button." `
    -Force | Out-Null
Write-Host "Registered 'WMS Pending Upload Sweep' (on-demand, no schedule)" -ForegroundColor Green

# --- Verify ---------------------------------------------------------------
Write-Host ""
foreach ($name in @("WMS Daily Backup", "WMS Weekly Restore Drill", "WMS Manual Backup", "WMS Pending Upload Sweep")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        $info = $t | Get-ScheduledTaskInfo
        "  {0,-26} {1}  next={2}" -f $t.TaskName, $t.State, $info.NextRunTime
    }
}
Write-Host "`nDone. Backups + DR drill are scheduled and reproducible." -ForegroundColor Green

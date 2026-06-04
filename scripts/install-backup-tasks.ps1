#Requires -Version 5.1
<#
.SYNOPSIS
    Register the WMS scheduled tasks - daily encrypted backup + weekly restore
    drill - reproducibly and idempotently (Critical #7).

.DESCRIPTION
    Previously the daily backup was a hand-made Task Scheduler entry that did
    not survive a host rebuild. This script creates both tasks from source so
    a rebuilt machine restores the exact schedule:

      * "WMS Daily Backup"         - daily (default 13:00) -> backup-native.ps1
                                     (encrypted DB + filestore, retention, audit)
      * "WMS Weekly Restore Drill" - Sundays (default 03:00) -> restore-drill.ps1
                                     (decrypt + structural verify of the latest
                                     backup; never touches production)

    Tasks run as the current user when logged on, with missed-run catch-up
    (StartWhenAvailable). Re-running REPLACES the tasks (idempotent).

    Needs Administrator rights; relaunches itself elevated if necessary.

.PARAMETER BackupAt
    Daily backup time. Default "1:00PM".

.PARAMETER DrillAt
    Weekly drill time (Sunday). Default "3:00AM".

.EXAMPLE
    .\scripts\install-backup-tasks.ps1
#>
[CmdletBinding()]
param(
    [string]$BackupAt = "1:00PM",
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

$principal = New-ScheduledTaskPrincipal -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

# --- Daily backup ---------------------------------------------------------
$backupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $backupScript) `
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

# --- Verify ---------------------------------------------------------------
Write-Host ""
foreach ($name in @("WMS Daily Backup", "WMS Weekly Restore Drill")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        $info = $t | Get-ScheduledTaskInfo
        "  {0,-26} {1}  next={2}" -f $t.TaskName, $t.State, $info.NextRunTime
    }
}
Write-Host "`nDone. Backups + DR drill are scheduled and reproducible." -ForegroundColor Green

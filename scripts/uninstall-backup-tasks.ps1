#Requires -Version 5.1
<#
.SYNOPSIS
    Remove the WMS scheduled tasks created by install-backup-tasks.ps1
    (daily backup, weekly restore drill, on-demand manual backup), plus any
    stale one-shot "WMS Restore Once" task left behind by an interrupted
    gdrive-restore.ps1 -AsTask run. Self-elevating.

.EXAMPLE
    .\scripts\uninstall-backup-tasks.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $PSCommandPath)
    )
    return
}

foreach ($name in @("WMS Daily Backup", "WMS Weekly Restore Drill", "WMS Manual Backup", "WMS Restore Once")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed '$name'." -ForegroundColor Green
    } else {
        Write-Host "'$name' not found - nothing to do." -ForegroundColor Yellow
    }
}

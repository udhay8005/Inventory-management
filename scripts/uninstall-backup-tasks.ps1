#Requires -Version 5.1
<#
.SYNOPSIS
    Remove the WMS backup + restore-drill scheduled tasks created by
    install-backup-tasks.ps1. Self-elevating.

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

foreach ($name in @("WMS Daily Backup", "WMS Weekly Restore Drill")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed '$name'." -ForegroundColor Green
    } else {
        Write-Host "'$name' not found - nothing to do." -ForegroundColor Yellow
    }
}

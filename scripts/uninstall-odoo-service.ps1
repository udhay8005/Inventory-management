#Requires -Version 5.1
<#
.SYNOPSIS
    Stop and remove the Odoo (WMS) Windows service created by
    install-odoo-service.ps1.

.DESCRIPTION
    Needs Administrator rights; relaunches itself elevated if necessary.
    After removal, Odoo can still be started manually with start-native.ps1.

.PARAMETER ServiceName
    Service name to remove. Default 'Odoo-WMS'.

.EXAMPLE
    .\scripts\uninstall-odoo-service.ps1
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'Odoo-WMS'
)
$ErrorActionPreference = 'Stop'

# ─── Self-elevate ─────────────────────────────────────────────────────────
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath), '-ServiceName', $ServiceName
    )
    return
}

if (-not (Get-Service $ServiceName -ErrorAction SilentlyContinue)) {
    Write-Host "Service '$ServiceName' not found - nothing to do." -ForegroundColor Yellow
    return
}

$nssm = (Get-Command nssm.exe -ErrorAction SilentlyContinue).Source
$globs = @(
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*\*\win64\nssm.exe",
    'C:\Program Files\nssm*\win64\nssm.exe',
    'C:\ProgramData\chocolatey\bin\nssm.exe'
)
if (-not $nssm) {
    foreach ($g in $globs) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { $nssm = $hit.FullName; break }
    }
}

Write-Host "Removing service '$ServiceName'..." -ForegroundColor Cyan
if ($nssm) {
    & $nssm stop $ServiceName confirm 2>$null | Out-Null
    & $nssm remove $ServiceName confirm | Out-Null
} else {
    Stop-Service $ServiceName -Force -ErrorAction SilentlyContinue
    & sc.exe delete $ServiceName | Out-Null
}
Start-Sleep -Seconds 2

if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Service still present - a reboot may be required to finalize removal." -ForegroundColor DarkYellow
} else {
    Write-Host "Removed. Start Odoo manually with scripts\start-native.ps1 if needed." -ForegroundColor Green
}

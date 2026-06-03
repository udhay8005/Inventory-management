<#
.SYNOPSIS
    Stop any running native Odoo process (the one started by start-native.ps1).

.DESCRIPTION
    Looks for a python.exe inside .venv\ that's hosting odoo-bin and asks it
    to exit. Does NOT touch the PostgreSQL service.

.PARAMETER Force
    Kill rather than ask politely if the graceful shutdown doesn't work in 5s.
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPy = (Join-Path $ProjectRoot '.venv\Scripts\python.exe').ToLower()

$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower() -eq $VenvPy -and $_.CommandLine -match 'odoo-bin' }

if (-not $procs) {
    Write-Host "No native Odoo process found." -ForegroundColor DarkGray
    exit 0
}

foreach ($p in $procs) {
    Write-Host "Stopping Odoo PID $($p.ProcessId)..." -ForegroundColor Cyan
    if ($Force) {
        Stop-Process -Id $p.ProcessId -Force
    } else {
        Stop-Process -Id $p.ProcessId
    }
}

Write-Host "Done." -ForegroundColor Green

<#
.SYNOPSIS
    Run the out-of-process AI forecast worker natively (no Docker).

.DESCRIPTION
    Native replacement for the 'ai_worker' service from the old
    docker-compose.yml. Reads ai_worker/worker.py and runs it in the
    project's Python venv, with environment variables wired from .env
    (the script auto-loads .env if present).

    The worker connects to the locally-running Odoo via XML-RPC, fetches
    movement history, retrains a Holt-Winters / SES forecast per product,
    and writes the results back to wms.forecast. Loops every
    FORECAST_INTERVAL_HOURS hours.

    Run this in a separate PowerShell window from start-native.ps1, OR
    register it as a Windows service via NSSM (see docs/07-deployment.md).

.PARAMETER OdooUrl
    Full URL of the running Odoo server. Default: http://localhost:8069.

.PARAMETER DbName
    Odoo database name. Default: wms (or ODOO_DB from .env).

.PARAMETER User
    Odoo login the worker authenticates as. Needs read access to
    stock.move + write to wms.forecast. Default: admin.

.PARAMETER Password
    Odoo password for -User. Default: admin (or ODOO_USER_PASSWORD from .env).

.PARAMETER IntervalHours
    Hours between retraining cycles. Default: 6.

.EXAMPLE
    scripts\start-ai-worker.ps1

.EXAMPLE
    scripts\start-ai-worker.ps1 -IntervalHours 12 -User svc_ai
#>
[CmdletBinding()]
param(
    [string]$OdooUrl,
    [string]$DbName,
    [string]$User,
    [string]$Password,
    [int]$IntervalHours = 0
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPy      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$WorkerPy    = Join-Path $ProjectRoot 'ai_worker\worker.py'
$EnvFile     = Join-Path $ProjectRoot '.env'

if (-not (Test-Path $VenvPy)) {
    Write-Host "Python venv not found at $VenvPy" -ForegroundColor Red
    Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $WorkerPy)) {
    Write-Host "ai_worker/worker.py not found at $WorkerPy" -ForegroundColor Red
    exit 1
}

# Auto-load .env so the worker's env-var lookups (ODOO_URL etc.) succeed.
# Don't overwrite anything already set in the parent shell.
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$') {
            $name = $matches[1]; $value = $matches[2]
            if (-not [Environment]::GetEnvironmentVariable($name)) {
                Set-Item -Path "env:$name" -Value $value
            }
        }
    }
}

# Apply CLI overrides + sane defaults. The worker reads ODOO_URL / ODOO_DB
# / ODOO_USER / ODOO_PASSWORD / FORECAST_INTERVAL_HOURS, so we wire those.
# Note: .env uses ODOO_USER_PASSWORD for the password (matches old docker
# compose env-var mapping); the worker itself reads ODOO_PASSWORD. Map it.
if ($OdooUrl)       { $env:ODOO_URL = $OdooUrl }       elseif (-not $env:ODOO_URL)      { $env:ODOO_URL = 'http://localhost:8069' }
if ($DbName)        { $env:ODOO_DB = $DbName }         elseif (-not $env:ODOO_DB)       { $env:ODOO_DB = 'wms' }
if ($User)          { $env:ODOO_USER = $User }         elseif (-not $env:ODOO_USER)     { $env:ODOO_USER = 'admin' }
if ($Password)      { $env:ODOO_PASSWORD = $Password } elseif (-not $env:ODOO_PASSWORD) {
    # Fall back to .env's ODOO_USER_PASSWORD (docker-compose convention).
    $env:ODOO_PASSWORD = if ($env:ODOO_USER_PASSWORD) { $env:ODOO_USER_PASSWORD } else { 'admin' }
}
if ($IntervalHours -gt 0) { $env:FORECAST_INTERVAL_HOURS = "$IntervalHours" }
elseif (-not $env:FORECAST_INTERVAL_HOURS) { $env:FORECAST_INTERVAL_HOURS = '6' }

Write-Host "Starting AI forecast worker:" -ForegroundColor Cyan
Write-Host "    Odoo URL:    $env:ODOO_URL" -ForegroundColor Gray
Write-Host "    Database:    $env:ODOO_DB" -ForegroundColor Gray
Write-Host "    User:        $env:ODOO_USER" -ForegroundColor Gray
Write-Host "    Interval:    $env:FORECAST_INTERVAL_HOURS h" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $VenvPy $WorkerPy

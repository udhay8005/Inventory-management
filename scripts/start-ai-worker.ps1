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
    stock.move + write to wms.forecast. REQUIRED -- pass via -User or
    set ODOO_USER in .env. The script refuses to start as 'admin' or any
    other known placeholder (the worker must run as a low-privilege
    service account so its XML-RPC calls inherit minimal scope).

.PARAMETER Password
    Odoo password for -User. REQUIRED -- pass via -Password or set
    ODOO_USER_PASSWORD in .env (the worker itself reads ODOO_PASSWORD;
    the script maps one to the other). Placeholders like 'changeme*',
    'admin', or 'password' are rejected at startup.

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
            if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") { $value = $matches[1] }
            if (-not [Environment]::GetEnvironmentVariable($name)) {
                Set-Item -Path "env:$name" -Value $value
            }
        }
    }
}

# Placeholder detector mirrors install-native.ps1's. Kept inline (not
# extracted into a shared module) so this script stays self-contained --
# the cost of duplication here is one 8-line function; the benefit is
# zero coupling, instant revert.
$Script:PlaceholderPatterns = @(
    '^$',
    '^changeme.*',
    '^admin$',
    '^password$',
    '^local_master_pw$',
    '^example.*',
    '^test$',
    '^demo$',
    '^secret$',
    '^pass$'
)
function Test-IsPlaceholderSecret {
    param([string]$Value)
    if (-not $Value) { return $true }
    foreach ($pat in $Script:PlaceholderPatterns) {
        if ($Value -match $pat) { return $true }
    }
    return $false
}

# Apply CLI overrides, then resolve .env values. NO admin/admin fallback:
# the worker MUST run as a dedicated low-privilege Odoo user, because it
# connects via XML-RPC with whatever permissions that user has -- if it
# runs as admin, every controller it hits bypasses every ACL.
if ($OdooUrl) { $env:ODOO_URL = $OdooUrl } elseif (-not $env:ODOO_URL) { $env:ODOO_URL = 'http://localhost:8069' }
if ($DbName)  { $env:ODOO_DB  = $DbName  } elseif (-not $env:ODOO_DB)  { $env:ODOO_DB  = 'wms' }
if ($User)    { $env:ODOO_USER = $User }
if ($Password) {
    $env:ODOO_PASSWORD = $Password
} elseif (-not $env:ODOO_PASSWORD) {
    # .env uses ODOO_USER_PASSWORD (docker-compose convention); worker reads ODOO_PASSWORD.
    if ($env:ODOO_USER_PASSWORD) { $env:ODOO_PASSWORD = $env:ODOO_USER_PASSWORD }
}
if ($IntervalHours -gt 0) { $env:FORECAST_INTERVAL_HOURS = "$IntervalHours" }
elseif (-not $env:FORECAST_INTERVAL_HOURS) { $env:FORECAST_INTERVAL_HOURS = '6' }

# Hard fail on missing or placeholder credentials. The worker must not
# start with 'admin'/'admin' even in dev, because the env-var leak path
# from a worker process to a misconfigured production install is the kind
# of footgun that erases the entire two-role ACL design.
if (Test-IsPlaceholderSecret $env:ODOO_USER) {
    Write-Host ""
    Write-Host "ERROR: ODOO_USER is missing or a known placeholder ('admin', 'changeme*', etc.)." -ForegroundColor Red
    Write-Host "       The AI worker must run as a dedicated service user with minimal scope." -ForegroundColor Yellow
    Write-Host "       Create one in Odoo (Settings -> Users), then set in .env:" -ForegroundColor Yellow
    Write-Host "           ODOO_USER=svc_ai_forecast" -ForegroundColor White
    Write-Host "       Override per-invocation with -User <name>." -ForegroundColor DarkGray
    exit 1
}
if (Test-IsPlaceholderSecret $env:ODOO_PASSWORD) {
    Write-Host ""
    Write-Host "ERROR: ODOO_PASSWORD is missing or a known placeholder." -ForegroundColor Red
    Write-Host "       Set in .env (the worker reads ODOO_USER_PASSWORD):" -ForegroundColor Yellow
    Write-Host "           ODOO_USER_PASSWORD=<32+ random chars, no whitespace>" -ForegroundColor White
    Write-Host "       Generate with:" -ForegroundColor Yellow
    Write-Host "           -join ((1..32) | %{ '{0:x}' -f (Get-Random -Min 0 -Max 16) })" -ForegroundColor DarkGray
    Write-Host "       Override per-invocation with -Password <pw>." -ForegroundColor DarkGray
    exit 1
}

Write-Host "Starting AI forecast worker:" -ForegroundColor Cyan
Write-Host "    Odoo URL:    $env:ODOO_URL" -ForegroundColor Gray
Write-Host "    Database:    $env:ODOO_DB" -ForegroundColor Gray
Write-Host "    User:        $env:ODOO_USER" -ForegroundColor Gray
Write-Host "    Interval:    $env:FORECAST_INTERVAL_HOURS h" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $VenvPy $WorkerPy

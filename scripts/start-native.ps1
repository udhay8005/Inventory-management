<#
.SYNOPSIS
    Start the WMS Odoo server natively (no Docker).

.DESCRIPTION
    Activates the project's Python venv (.venv\), starts odoo-bin against
    the local PostgreSQL and the project's addons. Tail-follows the log.

.PARAMETER DbName
    Database to serve. Default: wms.

.PARAMETER Port
    HTTP port. Default: 8069.

.PARAMETER Upgrade
    Comma-separated list of modules to upgrade on startup, e.g.
    -Upgrade wms_repair_damage,wms_barcode.

.PARAMETER Dev
    Pass through Odoo's --dev flag for auto-reload + qweb debug.
    Example: -Dev "reload,qweb,xml"

.EXAMPLE
    scripts\start-native.ps1

.EXAMPLE
    scripts\start-native.ps1 -Upgrade wms_repair_damage -Dev "reload,qweb"

.NOTES
    Run scripts\install-native.ps1 first if .venv\ or .odoo\ don't exist.
#>
[CmdletBinding()]
param(
    [string]$DbName = 'wms',
    [int]$Port = 8069,
    [string]$Upgrade,
    [string]$Dev
)

$ErrorActionPreference = 'Stop'
$ProjectRoot   = Split-Path -Parent $PSScriptRoot
$OdooSrc       = Join-Path $ProjectRoot '.odoo'
$VenvPy        = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OdooBin       = Join-Path $OdooSrc 'odoo-bin'
$ConfPath      = Join-Path $ProjectRoot 'config\odoo.native.conf'

# ─── Sanity checks ────────────────────────────────────────────────────────
if (-not (Test-Path $VenvPy)) {
    Write-Host "Python venv not found at $VenvPy" -ForegroundColor Red
    Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $OdooBin)) {
    Write-Host "Odoo source not found at $OdooBin" -ForegroundColor Red
    Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $ConfPath)) {
    Write-Host "Native odoo.conf not found at $ConfPath" -ForegroundColor Red
    Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
    exit 1
}

# Auto-detect Postgres service (any 15/16/17). Start it if stopped.
$pgService = Get-Service -Name 'postgresql-x64-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if ($pgService -and $pgService.Status -ne 'Running') {
    Write-Host "Starting $($pgService.Name) service..." -ForegroundColor Cyan
    Start-Service $pgService.Name
}

# Make sure wkhtmltopdf is on PATH so Odoo's PDF report engine finds it.
# Without this, Print actions fall back to HTML mode and labels look broken.
$wkPaths = @(
    'C:\Program Files\wkhtmltopdf\bin',
    'C:\Program Files (x86)\wkhtmltopdf\bin'
)
foreach ($p in $wkPaths) {
    if ((Test-Path "$p\wkhtmltopdf.exe") -and ($env:Path -notlike "*$p*")) {
        $env:Path = "$p;$env:Path"
    }
}

# Same idea for Postgres tools (pg_dump in the venv-shell context, etc.).
$pgBin = 'C:\Program Files\PostgreSQL\17\bin'
if ((Test-Path "$pgBin\psql.exe") -and ($env:Path -notlike "*$pgBin*")) {
    $env:Path = "$pgBin;$env:Path"
}

# ─── Build command line ───────────────────────────────────────────────────
$odooArgs = @('-c', $ConfPath, '-d', $DbName, '--http-port', $Port)
if ($Upgrade) { $odooArgs += @('-u', $Upgrade) }
if ($Dev)     { $odooArgs += @('--dev', $Dev) }

Write-Host "`nStarting Odoo on http://localhost:$Port (db=$DbName)" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor DarkGray

& $VenvPy $OdooBin @odooArgs

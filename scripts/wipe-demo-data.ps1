<#
.SYNOPSIS
    Remove the 5 demo products + every dependent record.

.DESCRIPTION
    Calls scripts/_wipe_demo_data.py against the running Odoo. The
    Python helper walks the dependency graph from the leaves up
    (repair orders -> damages -> moves -> quants -> aliases ->
    forecasts -> products) and finishes by resetting the per-kind
    SKU sequences so the trust's first real product starts at
    TOOL-00001 / CONS-00001 / etc.

    Run a -DryRun first if you want to see counts before committing.

.PARAMETER DryRun
    Just print how many rows WOULD be unlinked, don't touch anything.

.EXAMPLE
    scripts\wipe-demo-data.ps1 -DryRun
    scripts\wipe-demo-data.ps1
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force,
    [string]$DbName   = 'wms',
    [string]$Login    = 'admin',
    [string]$Password = 'admin',
    [string]$Url      = 'http://localhost:8069'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SqlFile  = Join-Path $PSScriptRoot '_wipe_demo_data.sql'
$ConfPath = Join-Path $ProjectRoot 'config\odoo.native.conf'

if (-not (Test-Path $SqlFile))  { Write-Host "SQL helper missing: $SqlFile"; exit 1 }
if (-not (Test-Path $ConfPath)) { Write-Host "odoo.native.conf missing: $ConfPath"; exit 1 }

# Resolve PG connection from odoo.native.conf -- the trust runs on
# 1088 by default, not 5432.
function Get-Conf([string]$key) {
    $line = Select-String -Path $ConfPath -Pattern "^${key}\s*=\s*(.+)$" | Select-Object -First 1
    if ($line) { return $line.Matches.Groups[1].Value.Trim() }
    return $null
}
$DbHost = Get-Conf 'db_host'
$DbPort = Get-Conf 'db_port'
$DbUser = Get-Conf 'db_user'
$env:PGPASSWORD = Get-Conf 'db_password'

if (-not $DbHost) { $DbHost = 'localhost' }
if (-not $DbPort) { $DbPort = '5432' }
if (-not $DbUser) { $DbUser = 'odoo' }

$psql = (Get-Command psql.exe -ErrorAction SilentlyContinue)
if (-not $psql) {
    $cand = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
    if (Test-Path $cand) { $env:Path = "C:\Program Files\PostgreSQL\17\bin;$env:Path" }
    else { Write-Host "psql.exe not found on PATH or in PG\17\bin"; exit 1 }
}

if (-not $DryRun -and -not $Force) {
    Write-Host ""
    Write-Host "This will permanently delete:" -ForegroundColor Yellow
    Write-Host "  - 5 demo products (DRILL-18V, HELMET-01, NUT-M4, SCRW-M4-20, TIE-200)" -ForegroundColor Yellow
    Write-Host "  - every damage / repair / move / quant / alias that references them" -ForegroundColor Yellow
    Write-Host "  - resets per-kind SKU sequences to 1" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Take a backup first (scripts\backup-native.ps1), then re-run with -Force." -ForegroundColor Cyan
    Write-Host "  scripts\wipe-demo-data.ps1 -Force" -ForegroundColor Cyan
    exit 1
}

if ($DryRun) {
    Write-Host "Dry run: counting demo data that WOULD be wiped..." -ForegroundColor Cyan
    & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -c @"
SELECT 'products' AS what, COUNT(*) FROM product_template WHERE default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200')
UNION ALL SELECT 'damages on demo prods', COUNT(*) FROM wms_damage     WHERE product_id IN (SELECT pp.id FROM product_product pp JOIN product_template pt ON pt.id=pp.product_tmpl_id WHERE pt.default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200'))
UNION ALL SELECT 'repairs on demo prods', COUNT(*) FROM wms_repair_order WHERE product_id IN (SELECT pp.id FROM product_product pp JOIN product_template pt ON pt.id=pp.product_tmpl_id WHERE pt.default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200'))
UNION ALL SELECT 'stock_move rows',     COUNT(*) FROM stock_move WHERE product_id IN (SELECT pp.id FROM product_product pp JOIN product_template pt ON pt.id=pp.product_tmpl_id WHERE pt.default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200'))
UNION ALL SELECT 'stock_quant rows',    COUNT(*) FROM stock_quant WHERE product_id IN (SELECT pp.id FROM product_product pp JOIN product_template pt ON pt.id=pp.product_tmpl_id WHERE pt.default_code IN ('DRILL-18V','HELMET-01','NUT-M4','SCRW-M4-20','TIE-200'));
"@
    exit 0
}

Write-Host "Running SQL wipe via psql..." -ForegroundColor Cyan
& psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -v ON_ERROR_STOP=1 -f $SqlFile
exit $LASTEXITCODE

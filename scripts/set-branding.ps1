<#
.SYNOPSIS
    Upload company logo + favicon to res.company in the running Odoo.

.DESCRIPTION
    Reads branding/logo.png and branding/favicon.png from the project
    root and pushes them onto the main company via XML-RPC. Re-run
    any time to refresh - replacing branding/logo.png is enough; no
    Odoo restart is needed because both fields are stored attachments.

.PARAMETER LogoPath
    Override the default logo path (branding/logo.png).

.PARAMETER FaviconPath
    Override the default favicon path (branding/favicon.png).

.PARAMETER DbName, Login, Password, Url
    Connection overrides. Defaults match the local native install.

.EXAMPLE
    scripts\set-branding.ps1

.EXAMPLE
    scripts\set-branding.ps1 -LogoPath 'D:\my-new-logo.jpg'
#>
[CmdletBinding()]
param(
    [string]$LogoPath,
    [string]$FaviconPath,
    [string]$DbName   = 'wms',
    [string]$Login    = 'admin',
    [string]$Password = 'admin',
    [string]$Url      = 'http://localhost:8069'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (-not $LogoPath)    { $LogoPath    = Join-Path $ProjectRoot 'branding\logo.png' }
if (-not $FaviconPath) { $FaviconPath = Join-Path $ProjectRoot 'branding\favicon.png' }

# Sanity check: file existence.
$missing = @()
if (-not (Test-Path $LogoPath))    { $missing += $LogoPath }
if (-not (Test-Path $FaviconPath)) { $missing += $FaviconPath }
if ($missing.Count) {
    Write-Host "Branding file(s) missing:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  $_" }
    Write-Host "Drop the file(s) at those paths, then re-run." -ForegroundColor Yellow
    exit 1
}

# Use the project venv so xmlrpc.client comes from the same Python that
# Odoo is running under (avoids version-skew surprises).
$VenvPy = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    Write-Host "Project venv not found at $VenvPy" -ForegroundColor Red
    Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
    exit 1
}

$PyHelper = Join-Path $PSScriptRoot '_set_branding.py'
if (-not (Test-Path $PyHelper)) {
    Write-Host "Helper $PyHelper missing - re-pull this scripts folder." -ForegroundColor Red
    exit 1
}

& $VenvPy $PyHelper $Url $DbName $Login $Password $LogoPath $FaviconPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Reload your browser tab to see the new logo and favicon." -ForegroundColor Green

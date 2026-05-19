<#
.SYNOPSIS
    One-shot installer for running the WMS natively on Windows - no Docker.

.DESCRIPTION
    Installs PostgreSQL 16 + Python 3.12 + wkhtmltopdf via winget,
    clones Odoo 19.0 source into .odoo/, creates a Python venv at .venv/,
    pip-installs every dependency (Odoo's own + this project's extras),
    creates the wms database, and runs Odoo's first-time init.

    Idempotent - re-running skips anything that's already in place. Use
    -Reset to wipe the cloned Odoo source + venv and start over.

    After this finishes, start the server with:
        scripts\start-native.ps1

.PARAMETER Reset
    Delete .odoo\ and .venv\ before re-installing. Database is left alone.

.PARAMETER SkipWinget
    Skip the PostgreSQL / Python / wkhtmltopdf install steps. Useful if you
    already have those installed manually.

.PARAMETER DbName
    Name of the Odoo database to create. Default: wms.

.PARAMETER DbPassword
    Password to set for the local 'odoo' Postgres user. Default: read from
    .env (DB_PASSWORD), else 'odoo_local_dev_pw'.

.EXAMPLE
    scripts\install-native.ps1

.EXAMPLE
    scripts\install-native.ps1 -Reset

.NOTES
    Requires: Windows 10/11, PowerShell 5.1+, admin rights for winget installs,
              ~5 GB free disk for Odoo source + venv + Postgres data.
#>
[CmdletBinding()]
param(
    [switch]$Reset,
    [switch]$SkipWinget,
    [string]$DbName = 'wms',
    [string]$DbPassword
)

$ErrorActionPreference = 'Stop'
$ProjectRoot   = Split-Path -Parent $PSScriptRoot
$OdooSrc       = Join-Path $ProjectRoot '.odoo'
$VenvDir       = Join-Path $ProjectRoot '.venv'
$RuntimeDir    = Join-Path $ProjectRoot '.runtime'
$DataDir       = Join-Path $RuntimeDir 'data'
$LogDir        = Join-Path $RuntimeDir 'logs'
$ConfPath      = Join-Path $ProjectRoot 'config\odoo.native.conf'
$EnvPath       = Join-Path $ProjectRoot '.env'

function Write-Step($msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Skip($msg) {
    Write-Host "    [skip] $msg" -ForegroundColor DarkGray
}

# Resolve DB password from .env if not supplied.
if (-not $DbPassword) {
    if (Test-Path $EnvPath) {
        $envLine = (Select-String -Path $EnvPath -Pattern '^DB_PASSWORD=(.+)$' | Select-Object -First 1)
        if ($envLine) {
            $DbPassword = $envLine.Matches.Groups[1].Value.Trim()
        }
    }
    if (-not $DbPassword) {
        $DbPassword = 'odoo_local_dev_pw'
    }
}

# === Reset if requested ====================================================
if ($Reset) {
    Write-Step "Reset requested - removing .odoo and .venv"
    if (Test-Path $OdooSrc) {
        Remove-Item -Recurse -Force $OdooSrc
        Write-OK "Deleted $OdooSrc"
    }
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
        Write-OK "Deleted $VenvDir"
    }
}

# === 1. winget-installed prerequisites =====================================
if (-not $SkipWinget) {
    Write-Step "Installing system prerequisites (PostgreSQL 16, Python 3.12, wkhtmltopdf, Git)"

    # winget itself
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available. Install 'App Installer' from the Microsoft Store first, then re-run this script."
    }

    $packages = @(
        @{ Id='PostgreSQL.PostgreSQL.16'; Probe={ Get-Command psql -ErrorAction SilentlyContinue } },
        @{ Id='Python.Python.3.12';      Probe={ (Get-Command py -ErrorAction SilentlyContinue) -and (py -3.12 --version 2>$null) } },
        @{ Id='wkhtmltopdf.wkhtmltox';   Probe={ Get-Command wkhtmltopdf -ErrorAction SilentlyContinue } },
        @{ Id='Git.Git';                 Probe={ Get-Command git -ErrorAction SilentlyContinue } }
    )

    foreach ($pkg in $packages) {
        if (& $pkg.Probe) {
            Write-Skip "$($pkg.Id) already installed"
        } else {
            Write-Host "    Installing $($pkg.Id) via winget..."
            winget install --id $pkg.Id --silent --accept-package-agreements --accept-source-agreements
            Write-OK "$($pkg.Id) installed"
        }
    }

    # Refresh PATH for this session so subsequent commands see the new binaries.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
}

# === 2. PostgreSQL - service + role + DB ===================================
Write-Step "Configuring PostgreSQL"

$pgService = Get-Service -Name 'postgresql-x64-16' -ErrorAction SilentlyContinue
if (-not $pgService) {
    throw "PostgreSQL 16 service 'postgresql-x64-16' not found. Install PostgreSQL via winget or run with -SkipWinget after manual install."
}
if ($pgService.Status -ne 'Running') {
    Start-Service postgresql-x64-16
    Write-OK "Started postgresql-x64-16 service"
} else {
    Write-Skip "postgresql-x64-16 already running"
}

# Create 'odoo' role + grant CREATEDB. Use the 'postgres' superuser via PGPASSWORD env (set during winget install or by user).
# If the postgres user has no password yet, the user must set one first; we print clear guidance instead of failing silently.
$psqlCheck = & psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='odoo'" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Cannot reach Postgres as 'postgres' user." -ForegroundColor Yellow
    Write-Host "    Set PGPASSWORD in this shell to the postgres superuser password, then re-run:" -ForegroundColor Yellow
    Write-Host "        `$env:PGPASSWORD = '<your-postgres-password>'" -ForegroundColor Yellow
    Write-Host "        scripts\install-native.ps1 -SkipWinget" -ForegroundColor Yellow
    throw "Postgres auth failed."
}

if ($psqlCheck -ne '1') {
    & psql -U postgres -d postgres -c "CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD '$DbPassword';" | Out-Null
    Write-OK "Created Postgres role 'odoo' with CREATEDB"
} else {
    & psql -U postgres -d postgres -c "ALTER ROLE odoo WITH PASSWORD '$DbPassword' CREATEDB;" | Out-Null
    Write-OK "Updated password + CREATEDB on existing 'odoo' role"
}

$dbExists = & psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'" 2>$null
if ($dbExists -ne '1') {
    & psql -U postgres -d postgres -c "CREATE DATABASE $DbName OWNER odoo;" | Out-Null
    Write-OK "Created database '$DbName' owned by odoo"
} else {
    Write-Skip "Database '$DbName' already exists"
}

# === 3. Clone Odoo 19.0 source =============================================
Write-Step "Cloning Odoo 19.0 source"

if (Test-Path (Join-Path $OdooSrc 'odoo-bin')) {
    Write-Skip "Odoo source already at $OdooSrc"
} else {
    & git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git $OdooSrc
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
    Write-OK "Cloned Odoo 19.0 to $OdooSrc"
}

# === 4. Python venv + dependencies =========================================
Write-Step "Creating Python venv + installing dependencies (~5 min the first time)"

if (-not (Test-Path (Join-Path $VenvDir 'Scripts\python.exe'))) {
    & py -3.12 -m venv $VenvDir
    Write-OK "Created venv at $VenvDir"
} else {
    Write-Skip "Venv already exists at $VenvDir"
}

$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'
$VenvPip = Join-Path $VenvDir 'Scripts\pip.exe'

& $VenvPy -m pip install --upgrade pip setuptools wheel | Out-Null
Write-OK "Upgraded pip/setuptools/wheel"

# Odoo's own requirements file. We swap psycopg2 -> psycopg2-binary on Windows
# (avoids needing Visual C++ Build Tools).
$OdooReq = Join-Path $OdooSrc 'requirements.txt'
$OdooReqWin = Join-Path $RuntimeDir 'odoo-requirements-win.txt'
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
(Get-Content $OdooReq) `
    -replace '^psycopg2(==|>=|<=|~=|!=).*$', 'psycopg2-binary' `
    -replace '^psycopg2$', 'psycopg2-binary' | Set-Content -Encoding utf8 $OdooReqWin

Write-Host "    Installing Odoo's Python deps (this is the long part)..."
& $VenvPip install -r $OdooReqWin
if ($LASTEXITCODE -ne 0) { throw "pip install of Odoo deps failed" }
Write-OK "Odoo dependencies installed"

# Project's extras (statsmodels, pandas, reportlab, etc.)
$ProjReq = Join-Path $ProjectRoot 'requirements.txt'
& $VenvPip install -r $ProjReq
if ($LASTEXITCODE -ne 0) { throw "pip install of project deps failed" }
Write-OK "Project extras installed"

# === 5. Runtime layout (data_dir + logs) ===================================
Write-Step "Preparing runtime directories"

foreach ($d in @($DataDir, $LogDir)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Write-OK "Created $d"
    } else {
        Write-Skip "$d already exists"
    }
}

# === 6. Native odoo.conf ===================================================
Write-Step "Writing native odoo.conf (config/odoo.native.conf)"

$confBody = @"
[options]
; Native (no-Docker) configuration. Generated by scripts/install-native.ps1.
; Re-run that script to regenerate.

admin_passwd = local_master_pw

addons_path = $($OdooSrc -replace '\\','/')/addons,$($ProjectRoot -replace '\\','/')/addons
data_dir = $($DataDir -replace '\\','/')

db_host = localhost
db_port = 5432
db_user = odoo
db_password = $DbPassword

; Threaded single-process server. WebSocket shares the HTTP port (8069).
workers = 0
max_cron_threads = 2

limit_memory_hard = 2147483648
limit_memory_soft = 1610612736
limit_time_cpu = 600
limit_time_real = 1200

proxy_mode = False
without_demo = False

log_level = info
log_handler = :INFO
logfile = $($LogDir -replace '\\','/')/odoo.log
"@

Set-Content -Path $ConfPath -Value $confBody -Encoding utf8
Write-OK "Wrote $ConfPath"

# === 7. First-time DB initialisation =======================================
Write-Step "Initialising the Odoo database (first run only)"

$OdooBin = Join-Path $OdooSrc 'odoo-bin'
$initMarker = Join-Path $RuntimeDir ".initialised-$DbName"

if (Test-Path $initMarker) {
    Write-Skip "Database '$DbName' already initialised (delete $initMarker to re-run)"
} else {
    Write-Host "    Running odoo-bin -i base --without-demo=all --stop-after-init..."
    & $VenvPy $OdooBin -c $ConfPath -d $DbName -i base --without-demo=all --stop-after-init --no-http
    if ($LASTEXITCODE -ne 0) { throw "Odoo first-time init failed" }
    New-Item -ItemType File -Path $initMarker | Out-Null
    Write-OK "Database '$DbName' initialised"
}

# === 8. Done ===============================================================
Write-Host "`n=== Install complete ===" -ForegroundColor Green
Write-Host "Database:       $DbName" -ForegroundColor Green
Write-Host "Config:         $ConfPath" -ForegroundColor Green
Write-Host "Odoo source:    $OdooSrc" -ForegroundColor Green
Write-Host "Python venv:    $VenvDir" -ForegroundColor Green
Write-Host "Data + logs:    $RuntimeDir" -ForegroundColor Green
Write-Host ""
Write-Host "Start the server:" -ForegroundColor Yellow
Write-Host "    scripts\start-native.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Then open http://localhost:8069 and install the WMS modules in this order:" -ForegroundColor Yellow
Write-Host "    wms_location  ->  wms_fifo  ->  wms_barcode  ->  wms_repair_damage  ->  wms_ai_forecast  ->  wms_reports" -ForegroundColor White

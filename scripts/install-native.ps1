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

.PARAMETER DbPort
    Port Postgres is listening on. Default: auto-detect from postgresql.conf,
    falling back to 5432.

.EXAMPLE
    scripts\install-native.ps1

.EXAMPLE
    scripts\install-native.ps1 -Reset -DbPort 1088

.NOTES
    Requires: Windows 10/11, PowerShell 5.1+, admin rights for winget installs,
              ~5 GB free disk for Odoo source + venv + Postgres data.
#>
[CmdletBinding()]
param(
    [switch]$Reset,
    [switch]$SkipWinget,
    [string]$DbName = 'wms',
    [string]$DbPassword,
    [int]$DbPort = 0
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

    # PostgreSQL: accept any 15/16/17 (script auto-detects the service later).
    # Python: prefer 3.12 (Odoo's tested version), accept 3.13 if installed.
    $packages = @(
        @{ Id='PostgreSQL.PostgreSQL.17'; Probe={ Get-Command psql -ErrorAction SilentlyContinue } },
        @{ Id='Python.Python.3.12';      Probe={ (Get-Command py -ErrorAction SilentlyContinue) -and ( (py -3.12 --version 2>$null) -or (py -3.13 --version 2>$null) ) } },
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

# Auto-detect whichever Postgres service is installed (15/16/17). Odoo 19
# works with all three; we just need ONE running locally.
$pgService = Get-Service -Name 'postgresql-x64-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $pgService) {
    throw "No PostgreSQL service found. Install PostgreSQL 15, 16, or 17 (e.g. winget install PostgreSQL.PostgreSQL.17) or run with -SkipWinget after manual install."
}
Write-OK "Detected PostgreSQL service: $($pgService.Name)"

if ($pgService.Status -ne 'Running') {
    Start-Service $pgService.Name
    Write-OK "Started $($pgService.Name)"
} else {
    Write-Skip "$($pgService.Name) already running"
}

# Auto-detect Postgres port from postgresql.conf if user didn't override.
if ($DbPort -eq 0) {
    $pgConf = Get-ChildItem 'C:\Program Files\PostgreSQL\*\data\postgresql.conf' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pgConf) {
        $portLine = Select-String -Path $pgConf.FullName -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
        if ($portLine) {
            $DbPort = [int]$portLine.Matches.Groups[1].Value
        }
    }
    if ($DbPort -eq 0) { $DbPort = 5432 }
}
Write-OK "Using Postgres on port $DbPort"

# Create 'odoo' role + grant CREATEDB. Use the 'postgres' superuser via PGPASSWORD env.
# The user must have set PGPASSWORD at User scope (or in this shell) for this to work
# - all auth methods are scram-sha-256 in modern PG installs, no trust path.
$psqlArgs = @('-U','postgres','-h','localhost','-p',$DbPort,'-d','postgres','-w')
$psqlCheck = & psql @psqlArgs -tAc "SELECT 1 FROM pg_roles WHERE rolname='odoo'" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Cannot reach Postgres as 'postgres' user on port $DbPort." -ForegroundColor Yellow
    Write-Host "    Set PGPASSWORD at User scope, then re-run:" -ForegroundColor Yellow
    Write-Host "        [Environment]::SetEnvironmentVariable('PGPASSWORD','<your-postgres-password>','User')" -ForegroundColor Yellow
    Write-Host "        scripts\install-native.ps1 -SkipWinget" -ForegroundColor Yellow
    throw "Postgres auth failed."
}

if ($psqlCheck -ne '1') {
    & psql @psqlArgs -c "CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD '$DbPassword';" | Out-Null
    Write-OK "Created Postgres role 'odoo' with CREATEDB"
} else {
    & psql @psqlArgs -c "ALTER ROLE odoo WITH PASSWORD '$DbPassword' CREATEDB;" | Out-Null
    Write-OK "Updated password + CREATEDB on existing 'odoo' role"
}

$dbExists = & psql @psqlArgs -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName'" 2>$null
if ($dbExists -ne '1') {
    & psql @psqlArgs -c "CREATE DATABASE $DbName OWNER odoo;" | Out-Null
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
    # Prefer Python 3.12 (Odoo's tested baseline). Fall back to 3.13.
    # py -0 lists every Python the launcher knows about; safer than running
    # py -3.X --version which throws under ErrorActionPreference=Stop when
    # that version isn't installed.
    $pyList = ''
    try { $pyList = (py -0 2>&1 | Out-String) } catch { $pyList = '' }
    $pyVer = $null
    # Prefer 3.12 > 3.11 > 3.13. Odoo 19's pinned requirements (e.g.
    # rl-renderPM 4.0.3) don't build on 3.13 because the old wheel API
    # they call (wheel.bdist_wheel.get_abi_tag) was removed. 3.11 + 3.12
    # work cleanly with the published wheels.
    if ($pyList -match '(?m)^\s*-V:?3\.12') { $pyVer = '3.12' }
    elseif ($pyList -match '(?m)^\s*-V:?3\.11') { $pyVer = '3.11' }
    elseif ($pyList -match '(?m)^\s*-V:?3\.13') { $pyVer = '3.13' }
    else {
        Write-Host "py -0 output:" -ForegroundColor Yellow
        Write-Host $pyList
        throw "No usable Python (3.11/3.12/3.13) found via the 'py' launcher. Install Python 3.12 from python.org or via 'winget install Python.Python.3.12'."
    }
    Write-OK "Using Python $pyVer for the venv"
    & py "-$pyVer" -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "py -$pyVer -m venv failed (exit $LASTEXITCODE)" }
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
db_port = $DbPort
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

# Use .NET's WriteAllText with explicit no-BOM UTF-8 because
# Set-Content -Encoding utf8 prepends a BOM that Python's configparser
# can't read (raises MissingSectionHeaderError on the first [options]).
[System.IO.File]::WriteAllText($ConfPath, $confBody, [System.Text.UTF8Encoding]::new($false))
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

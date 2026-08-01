<#
.SYNOPSIS
    Rebuild the WMS database from scratch on the CURRENT code: drop it, create
    it empty, install all ten addons, restart the service.

.DESCRIPTION
    This DESTROYS every record in the database - products, locations, stock,
    batches, issues, returns, audits, damage and repair history, users and
    passwords. It is for starting clean (finished piloting, want a fresh
    production database), NOT for updating.

    To keep your data and move to the latest code, use upgrade-service.ps1
    instead. That is the normal path and it is the one you almost always want.

    What this script does, in order:
      1. takes a full encrypted backup (unless -SkipBackup), so the data you
         are about to destroy is recoverable
      2. makes you type the database name to confirm (unless -Force)
      3. stops the Odoo service so nothing is holding the database open
      4. terminates any leftover connections, then drops the database
      5. creates it empty and installs all ten WMS addons with --without-demo
      6. starts the service again and checks it is listening

    install-native.ps1 -Reset does NOT do this: it wipes the cloned Odoo source
    and the venv, and leaves the database untouched. That difference has bitten
    people, hence this script.

.PARAMETER DbName       Database to rebuild. Default 'wms'.
.PARAMETER ServiceName  Windows service to stop/start. Default 'Odoo-WMS'.
.PARAMETER Port         Port the service listens on. Default 8069.
.PARAMETER Modules      Addons to install. Default: all ten.
.PARAMETER Force        Skip the typed confirmation. For unattended runs only.
.PARAMETER SkipBackup   Do not back up first. Strongly discouraged.

.EXAMPLE
    # Normal use: rebuild 'wms' clean, with a backup and a confirmation prompt
    .\scripts\reset-database.ps1

.EXAMPLE
    # Rebuild a throwaway test database without prompting
    .\scripts\reset-database.ps1 -DbName wms_scratch -Force -SkipBackup
#>
param(
    [string]$DbName = 'wms',
    [string]$ServiceName = 'Odoo-WMS',
    [int]$Port = 8069,
    [string]$Modules = 'wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports,wms_training,wms_perishable,wms_analytics,wms_pharmacy',
    [switch]$Force,
    [switch]$SkipBackup
)

$ErrorActionPreference = 'Stop'

function Write-Step { param($m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-OK   { param($m) Write-Host "    [ok] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "    [!] $m" -ForegroundColor Yellow }

# --- self-elevate (same pattern as upgrade-service.ps1) -------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    $relaunch = @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-DbName', $DbName, '-ServiceName', $ServiceName, '-Port', "$Port", '-Modules', $Modules
    )
    if ($Force) { $relaunch += '-Force' }
    if ($SkipBackup) { $relaunch += '-SkipBackup' }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $relaunch
    return
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPy   = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OdooBin  = Join-Path $ProjectRoot '.odoo\odoo-bin'
$ConfPath = Join-Path $ProjectRoot 'config\odoo.native.conf'
$BackupPs = Join-Path $ProjectRoot 'scripts\backup-native.ps1'
$LogDir   = Join-Path $ProjectRoot '.runtime\logs'
foreach ($p in @($VenvPy, $OdooBin, $ConfPath)) {
    if (-not (Test-Path $p)) { throw "Missing required path: $p  (run install-native.ps1 first)" }
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Connection details come from the same conf Odoo uses, so this can never
# operate on a different server than the one the app talks to.
$conf = Get-Content -LiteralPath $ConfPath
function Get-Conf { param($key, $default)
    $line = $conf | Where-Object { $_ -match "^\s*$key\s*=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1].Trim() }
    return $default
}
$DbHost = Get-Conf 'db_host' 'localhost'
$DbPort = Get-Conf 'db_port' '5432'
$DbUser = Get-Conf 'db_user' 'odoo'
$DbPass = Get-Conf 'db_password' ''

$psqlExe = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psqlExe) { throw "psql not found on PATH. Install PostgreSQL client tools or add them to PATH." }

Write-Host ""
Write-Host "  ############################################################" -ForegroundColor Red
Write-Host "  #  THIS DESTROYS ALL DATA IN THE DATABASE '$DbName'" -ForegroundColor Red
Write-Host "  #  products - locations - stock - batches - issues - returns" -ForegroundColor Red
Write-Host "  #  audits - damage/repair history - users and passwords" -ForegroundColor Red
Write-Host "  #" -ForegroundColor Red
Write-Host "  #  To KEEP your data and just move to the latest code, stop" -ForegroundColor Red
Write-Host "  #  now and run scripts\upgrade-service.ps1 instead." -ForegroundColor Red
Write-Host "  ############################################################" -ForegroundColor Red
Write-Host ""
Write-Host "  server : $DbHost`:$DbPort   user: $DbUser"
Write-Host "  modules: $Modules"
Write-Host ""

# --- 1. backup ------------------------------------------------------------
if (-not $SkipBackup) {
    Write-Step "Backing up '$DbName' before destroying it"
    if (-not (Test-Path $BackupPs)) { throw "backup-native.ps1 not found - refusing to drop a database with no backup. Pass -SkipBackup only if you are certain." }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BackupPs -DbName $DbName
    if ($LASTEXITCODE -ne 0) { throw "Backup failed (exit $LASTEXITCODE). Aborting - nothing has been dropped." }
    Write-OK "Backup complete; the data being destroyed is recoverable"
} else {
    Write-Warn "-SkipBackup: no rollback point. Anything in '$DbName' is gone for good."
}

# --- 2. confirmation ------------------------------------------------------
if (-not $Force) {
    Write-Host ""
    $typed = Read-Host "Type the database name '$DbName' to confirm permanent deletion"
    if ($typed -ne $DbName) {
        Write-Host "Confirmation did not match - nothing was changed." -ForegroundColor Yellow
        return
    }
}

# --- 3. stop the service --------------------------------------------------
Write-Step "Stopping '$ServiceName'"
$svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne 'Stopped') { Stop-Service $ServiceName -Force }
    for ($i = 0; $i -lt 30 -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue); $i++) {
        Start-Sleep -Seconds 1
    }
    Write-OK "Service stopped"
} else {
    Write-Warn "Service '$ServiceName' is not installed - continuing (start Odoo manually afterwards)"
}

# --- 4. drop + create -----------------------------------------------------
$env:PGPASSWORD = $DbPass
$psqlBase = @('-h', $DbHost, '-p', $DbPort, '-U', $DbUser, '-d', 'postgres', '-v', 'ON_ERROR_STOP=1')

Write-Step "Dropping database '$DbName'"
# Odoo keeps pooled connections; a single lingering one makes DROP DATABASE
# fail with "is being accessed by other users", so evict them first.
& $psqlExe @psqlBase -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DbName' AND pid <> pg_backend_pid();" | Out-Null
& $psqlExe @psqlBase -c "DROP DATABASE IF EXISTS $DbName;"
if ($LASTEXITCODE -ne 0) { throw "DROP DATABASE failed. The service may have restarted - stop it and re-run." }
Write-OK "Dropped"

Write-Step "Creating empty database '$DbName'"
& $psqlExe @psqlBase -c "CREATE DATABASE $DbName OWNER $DbUser;"
if ($LASTEXITCODE -ne 0) { throw "CREATE DATABASE failed." }
Write-OK "Created"

# The filestore belongs to the old database; leaving it behind means orphaned
# attachments and stale label logos in the fresh one.
$FileStore = Join-Path $env:LOCALAPPDATA "Odoo\filestore\$DbName"
if (Test-Path $FileStore) {
    Remove-Item -Recurse -Force $FileStore
    Write-OK "Removed the old filestore"
}

# --- 5. install the addons ------------------------------------------------
Write-Step "Installing all WMS addons (this takes a few minutes)"
# Odoo writes to .runtime\logs per config/odoo.native.conf, so there is no
# separate log file to manage here.
& $VenvPy $OdooBin -c $ConfPath -d $DbName -i $Modules --without-demo=all --stop-after-init
if ($LASTEXITCODE -ne 0) { throw "Module installation failed (exit $LASTEXITCODE). See $LogDir for the Odoo log." }
Write-OK "All addons installed on a clean database"

# --- 6. restart + verify --------------------------------------------------
if ($svc) {
    Write-Step "Starting '$ServiceName'"
    Start-Service $ServiceName
    $listening = $false
    for ($i = 0; $i -lt 60; $i++) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { $listening = $true; break }
        Start-Sleep -Seconds 1
    }
    if ($listening) { Write-OK "Service is listening on port $Port" }
    else { Write-Warn "Service started but nothing is listening on $Port yet - check $LogDir" }
}

Write-Host ""
Write-Host "  Done. '$DbName' is a clean database on the current code." -ForegroundColor Green
Write-Host "  Sign in at http://localhost:$Port as admin / admin and CHANGE THAT PASSWORD." -ForegroundColor Yellow
Write-Host "  Then rebuild your storage structure and load stock." -ForegroundColor Yellow
Write-Host ""

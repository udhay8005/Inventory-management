#Requires -Version 5.1
<#
.SYNOPSIS
    Safely apply a code upgrade to the service-mode Odoo WMS: optional pre-upgrade
    backup, stop the service, run the Odoo module upgrade, restart the service,
    and verify /wms/health.

.DESCRIPTION
    Upgrading the live service by hand is fragile (stop the right service,
    remember the -u flags, restart, hope health returns). This does it
    reproducibly and reversibly:

      1. (unless -SkipBackup) run backup-native.ps1 so there is a rollback point
      2. stop the Odoo-WMS service and wait for the port to free
      3. run `odoo -c <conf> -d <db> -u <modules> --stop-after-init` in the venv
      4. start the service again
      5. poll /wms/health until it answers (or fail loudly, pointing at the
         backup + logs for rollback)

    Deploy the new CODE first (git pull / copy), then run this to migrate the DB
    and bounce the service. Needs Administrator rights; self-elevates.

.PARAMETER ServiceName  Default 'Odoo-WMS'.
.PARAMETER DbName       Default 'wms'.
.PARAMETER Port         Default 8069.
.PARAMETER Modules      Comma-separated modules to upgrade/install. Default: the WMS set.
.PARAMETER Install      Install (-i) the modules instead of upgrading (-u). Use for a
                        NOT-yet-installed module - it creates the module's tables,
                        menus and ACLs. Safe to re-run (a no-op on installed modules).
.PARAMETER SkipBackup   Skip the pre-upgrade backup (NOT recommended).
.PARAMETER HealthToken  Value of ir.config_parameter wms_reports.health_token, if
                        one is configured. Passed to /wms/health so the poll can
                        read the real HEALTHY/DEGRADED/CRITICAL status. Optional:
                        when omitted, a 401 from the token-gated endpoint is still
                        correctly treated as "service is up".

.EXAMPLE
    .\scripts\upgrade-service.ps1
.EXAMPLE
    .\scripts\upgrade-service.ps1 -Modules wms_barcode,wms_reports
.EXAMPLE
    # Install a not-yet-installed module (e.g. a Wave rollout):
    .\scripts\upgrade-service.ps1 -Modules wms_perishable,wms_analytics -Install
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'Odoo-WMS',
    [string]$DbName = 'wms',
    [int]$Port = 8069,
    [string]$Modules = 'wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports,wms_training',
    [switch]$Install,
    [switch]$SkipBackup,
    [string]$HealthToken = ''
)
$ErrorActionPreference = 'Stop'

# --- self-elevate ---------------------------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    $relaunch = @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-ServiceName', $ServiceName, '-DbName', $DbName, '-Port', "$Port", '-Modules', $Modules
    )
    if ($SkipBackup) { $relaunch += '-SkipBackup' }
    if ($Install) { $relaunch += '-Install' }
    if ($HealthToken) { $relaunch += @('-HealthToken', $HealthToken) }
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

# --- 1. pre-upgrade backup (rollback point) -------------------------------
if (-not $SkipBackup) {
    if (Test-Path $BackupPs) {
        Write-Host "Taking a pre-upgrade backup (rollback point)..." -ForegroundColor Cyan
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BackupPs
        if ($LASTEXITCODE -ne 0) {
            throw "Pre-upgrade backup failed (exit $LASTEXITCODE). Aborting; fix the backup or pass -SkipBackup to override."
        }
    } else {
        Write-Host "backup-native.ps1 not found; continuing WITHOUT a pre-upgrade backup." -ForegroundColor Yellow
    }
}

# --- 2. stop the service --------------------------------------------------
$svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Stopping service '$ServiceName'..." -ForegroundColor Cyan
    Stop-Service $ServiceName -Force
    for ($i = 0; $i -lt 20 -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue); $i++) {
        Start-Sleep -Seconds 1
    }
} else {
    Write-Host "Service '$ServiceName' not installed; upgrading the DB directly (start Odoo manually afterwards)." -ForegroundColor Yellow
}

# --- 3. run the upgrade / install -----------------------------------------
# -Install (-i) initialises a NOT-yet-installed module (creates its tables,
# menus, ACLs); the default (-u) upgrades already-installed modules. Odoo
# treats -i on an already-installed module as a no-op, so -Install is safe to
# re-run. Either way the service is stopped first, so this never races a live
# process against the DB (the failure mode of a manual `odoo-bin -i` while the
# service is up).
$odooFlag = if ($Install) { '-i' } else { '-u' }
$actionWord = if ($Install) { 'Installing' } else { 'Upgrading' }
Write-Host "$actionWord modules [$Modules] on '$DbName'..." -ForegroundColor Cyan
& $VenvPy $OdooBin -c $ConfPath -d $DbName $odooFlag $Modules --stop-after-init
$upgradeExit = $LASTEXITCODE
if ($upgradeExit -ne 0) {
    Write-Host "$actionWord FAILED (exit $upgradeExit). Service is stopped." -ForegroundColor Red
    if (-not $SkipBackup) {
        Write-Host "Restore the pre-upgrade backup via scripts\restore-drill.ps1 / your DR runbook if needed." -ForegroundColor Yellow
    }
    exit $upgradeExit
}

# --- 4. restart the service -----------------------------------------------
if ($svc) {
    Write-Host "Starting service '$ServiceName'..." -ForegroundColor Cyan
    Start-Service $ServiceName

    # --- 5. health check --------------------------------------------------
    # We poll until the HTTP server ANSWERS - that is what proves the upgrade
    # restarted cleanly. /wms/health is auth="public" but has an opt-in
    # shared-secret gate (ir.config_parameter wms_reports.health_token); when
    # that is set, a token-less GET returns 401. A 401/403 still proves the
    # service is up and the route exists, so we treat ANY HTTP status as
    # "responding" (only connection-refused / timeout keeps us waiting). Pass
    # -HealthToken to read the real HEALTHY/DEGRADED/CRITICAL status.
    $healthUrl = "http://localhost:$Port/wms/health"
    if ($HealthToken) { $healthUrl += "?token=$([uri]::EscapeDataString($HealthToken))" }
    Write-Host "Waiting for $healthUrl ..." -ForegroundColor Cyan
    $healthy = $false
    for ($i = 1; $i -le 36; $i++) {
        $code = $null; $body = $null
        try {
            $resp = Invoke-WebRequest $healthUrl -UseBasicParsing -TimeoutSec 5
            $code = [int]$resp.StatusCode; $body = $resp.Content
        } catch {
            # PS 5.1 throws on 4xx/5xx; the response (if any) carries the code.
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        }
        if ($code) {
            $secs = $i * 5
            if ($code -eq 200) {
                $status = try { ($body | ConvertFrom-Json).status } catch { 'OK' }
                Write-Host "  Healthy after ~${secs}s : $status (HTTP 200)" -ForegroundColor Green
            } elseif ($code -eq 503) {
                Write-Host "  Service up after ~${secs}s but health=CRITICAL (HTTP 503) - investigate /wms/health." -ForegroundColor Yellow
            } elseif ($code -in 401, 403) {
                Write-Host "  Service up after ~${secs}s (HTTP $code - /wms/health is token-gated; pass -HealthToken to read status)." -ForegroundColor Green
            } else {
                Write-Host "  Service responding after ~${secs}s (HTTP $code)." -ForegroundColor Green
            }
            $healthy = $true; break
        }
        Start-Sleep -Seconds 5
    }
    if (-not $healthy) {
        Write-Host "Upgrade applied but the service did not answer on $Port within 180s. Check $LogDir\service-err.log." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Done. Upgrade applied" -NoNewline -ForegroundColor Green
if ($svc) { Write-Host " and service healthy." -ForegroundColor Green } else { Write-Host "; start Odoo when ready." -ForegroundColor Green }

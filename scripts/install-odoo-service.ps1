#Requires -Version 5.1
<#
.SYNOPSIS
    Install Odoo (WMS) as an auto-starting Windows service with automatic
    restart-on-failure, using NSSM as the supervisor.

.DESCRIPTION
    Creates a Windows service ("Odoo-WMS" by default) that:
      * starts automatically on boot (SERVICE_AUTO_START),
      * runs the project's proven launcher (scripts\start-native.ps1) so the
        environment (PostgreSQL service, wkhtmltopdf / pg_dump on PATH) is set
        up exactly as a manual start,
      * is supervised by NSSM, which RESTARTS Odoo whenever it exits
        (5s delay, 5s crash-loop throttle),
      * also carries Windows-native recovery actions (sc.exe failure) as a
        second safety net,
      * writes rotating stdout/stderr logs to .runtime\logs\.

    The service runs as LocalSystem (no stored password needed). Database auth
    still uses the password in odoo.native.conf, so the OS identity is fine.

    NEEDS ADMINISTRATOR RIGHTS. If you launch it from a normal shell it will
    relaunch itself elevated (approve the single UAC prompt). NSSM is installed
    automatically via winget if it is not already present.

.PARAMETER ServiceName
    Service name. Default 'Odoo-WMS'.

.PARAMETER DbName
    Database to serve. Default 'wms'.

.PARAMETER Port
    HTTP port. Default 8069.

.EXAMPLE
    .\scripts\install-odoo-service.ps1
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'Odoo-WMS',
    [string]$DbName = 'wms',
    [int]$Port = 8069
)
$ErrorActionPreference = 'Stop'

# ─── Self-elevate ─────────────────────────────────────────────────────────
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    $relaunch = @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-ServiceName', $ServiceName, '-DbName', $DbName, '-Port', "$Port"
    )
    Start-Process powershell.exe -Verb RunAs -ArgumentList $relaunch
    return
}

# ─── Resolve paths ────────────────────────────────────────────────────────
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPy   = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OdooBin  = Join-Path $ProjectRoot '.odoo\odoo-bin'
$ConfPath = Join-Path $ProjectRoot 'config\odoo.native.conf'
$StartPs  = Join-Path $ProjectRoot 'scripts\start-native.ps1'
$LogDir   = Join-Path $ProjectRoot '.runtime\logs'
$PsExe    = (Get-Command powershell.exe).Source

foreach ($p in @($VenvPy, $OdooBin, $ConfPath, $StartPs)) {
    if (-not (Test-Path $p)) { throw "Missing required path: $p  (run install-native.ps1 first)" }
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ─── Ensure NSSM is available ─────────────────────────────────────────────
function Resolve-Nssm {
    $c = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $globs = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*\*\win64\nssm.exe",
        'C:\Program Files\nssm*\win64\nssm.exe',
        'C:\ProgramData\chocolatey\bin\nssm.exe'
    )
    foreach ($g in $globs) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$nssm = Resolve-Nssm
if (-not $nssm) {
    Write-Host "NSSM not found - installing via winget (NSSM.NSSM)..." -ForegroundColor Cyan
    try {
        winget install --id NSSM.NSSM --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity
    } catch {
        Write-Host "winget install reported: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
    $nssm = Resolve-Nssm
}
if (-not $nssm) {
    throw "Could not obtain nssm.exe. Install it manually (winget install NSSM.NSSM, or download from https://nssm.cc) then re-run."
}
Write-Host "Using NSSM: $nssm" -ForegroundColor DarkGray

# ─── Free port: stop any manually-running Odoo on the target port ─────────
$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($procId in ($listeners.OwningProcess | Sort-Object -Unique)) {
    $pp = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($pp -and $pp.ProcessName -match 'python') {
        Write-Host "Stopping manual Odoo on port $Port (pid $procId)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force
    }
}

# ─── Remove any prior service of the same name (idempotent re-install) ────
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing '$ServiceName' service for a clean re-install..." -ForegroundColor Yellow
    & $nssm stop $ServiceName confirm 2>$null | Out-Null
    & $nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

# ─── Install + configure ──────────────────────────────────────────────────
$appParams = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -DbName {1} -Port {2}' -f $StartPs, $DbName, $Port

& $nssm install $ServiceName $PsExe | Out-Null
& $nssm set $ServiceName AppParameters $appParams           | Out-Null
& $nssm set $ServiceName AppDirectory  $ProjectRoot         | Out-Null
& $nssm set $ServiceName DisplayName   "Odoo WMS ($DbName)" | Out-Null
& $nssm set $ServiceName Description   "Odoo 19 WMS (Dakshin Vrindavan). Auto-starts on boot; restarts on failure." | Out-Null
& $nssm set $ServiceName Start         SERVICE_AUTO_START   | Out-Null
# Logs (rotated at 10 MB)
& $nssm set $ServiceName AppStdout     (Join-Path $LogDir 'service-out.log') | Out-Null
& $nssm set $ServiceName AppStderr     (Join-Path $LogDir 'service-err.log') | Out-Null
& $nssm set $ServiceName AppRotateFiles 1         | Out-Null
& $nssm set $ServiceName AppRotateOnline 1        | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760  | Out-Null
# Restart-on-failure: relaunch on ANY exit, 5s delay, throttle rapid crash loops
& $nssm set $ServiceName AppExit Default Restart  | Out-Null
& $nssm set $ServiceName AppRestartDelay 5000     | Out-Null
& $nssm set $ServiceName AppThrottle 5000         | Out-Null
# Graceful stop: send Ctrl+C, wait up to 20s, then terminate the tree
& $nssm set $ServiceName AppStopMethodConsole 20000 | Out-Null

# Start after PostgreSQL so the DB is ready first
$pgSvc = Get-Service -Name 'postgresql-x64-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if ($pgSvc) { & $nssm set $ServiceName DependOnService $pgSvc.Name | Out-Null }

# Windows-native recovery actions (second safety net beyond NSSM)
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/60000 | Out-Null
& sc.exe failureflag $ServiceName 1 | Out-Null

# ─── Start + verify ───────────────────────────────────────────────────────
Write-Host "Starting service '$ServiceName'..." -ForegroundColor Cyan
Start-Service $ServiceName

Write-Host "Waiting for http://localhost:$Port/wms/health ..." -ForegroundColor Cyan
# Treat ANY HTTP response as "service is up" — only connection-refused/timeout
# keeps us waiting. /wms/health returns 404 before wms_reports is installed and
# 401 once the health token is set, so a 200-only gate false-fails a perfectly
# healthy install (exit 1). Mirrors the fixed upgrade-service.ps1 health gate.
$healthy = $false
for ($i = 1; $i -le 36; $i++) {
    $code = $null; $body = $null
    try {
        $resp = Invoke-WebRequest "http://localhost:$Port/wms/health" -UseBasicParsing -TimeoutSec 5
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
            Write-Host "  Service up after ~${secs}s but health=CRITICAL (HTTP 503) - check /wms/health." -ForegroundColor Yellow
        } elseif ($code -in 401, 403) {
            Write-Host "  Service up after ~${secs}s (HTTP $code - /wms/health is token-gated)." -ForegroundColor Green
        } else {
            Write-Host "  Service responding after ~${secs}s (HTTP $code)." -ForegroundColor Green
        }
        $healthy = $true; break
    }
    Start-Sleep -Seconds 5
}

$svc = Get-Service $ServiceName
Write-Host ""
Write-Host "  Service    : $($svc.Name)" -ForegroundColor White
Write-Host "  Status     : $($svc.Status)" -ForegroundColor White
Write-Host "  Start type : $($svc.StartType)  (Automatic = starts on boot)" -ForegroundColor White
Write-Host "  Recovery   : NSSM restart on exit + sc.exe failure actions" -ForegroundColor White
Write-Host "  Logs       : $LogDir" -ForegroundColor White
Write-Host ""
if (-not $healthy) {
    Write-Host "Service installed but health did not confirm in 180s. Check $LogDir\service-err.log." -ForegroundColor Red
    exit 1
}
Write-Host "Done. Odoo WMS runs as a service: starts on boot, restarts on failure." -ForegroundColor Green
Write-Host "Manage: Start-Service / Stop-Service / Restart-Service $ServiceName  (or services.msc)" -ForegroundColor Gray

#Requires -Version 5.1
<#
.SYNOPSIS
    Install the OPTIONAL out-of-process AI forecast worker as a supervised
    Windows service (NSSM) with automatic restart-on-failure.

.DESCRIPTION
    Forecasts run by default inside Odoo's own (supervised) daily cron, so the
    standalone worker is OFF unless you deliberately want forecasting off Odoo's
    RAM. When you do, running it by hand in a console (start-ai-worker.ps1) is
    unsupervised - it dies on logout and never restarts. This registers it as a
    service that NSSM restarts on exit, mirroring the Odoo-WMS service.

    Differences from the Odoo service, on purpose:
      * Start type is MANUAL (SERVICE_DEMAND_START). The worker refuses to run on
        placeholder credentials, so auto-starting it on boot before you have
        provisioned a real service account (ODOO_USER / ODOO_USER_PASSWORD in
        .env) would just crash-loop. Provision creds, then Start-Service.
      * Depends on the Odoo-WMS service (it talks to Odoo over XML-RPC).

    Needs Administrator rights; self-elevates. NSSM is installed via winget if
    absent.

.PARAMETER ServiceName  Default 'Odoo-WMS-AIWorker'.
.PARAMETER OdooService  Service this one depends on. Default 'Odoo-WMS'.
.PARAMETER IntervalHours  Hours between retraining cycles. Default 6.

.EXAMPLE
    .\scripts\install-ai-worker-service.ps1
    # then, after putting real creds in .env:
    Start-Service Odoo-WMS-AIWorker
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'Odoo-WMS-AIWorker',
    [string]$OdooService = 'Odoo-WMS',
    [int]$IntervalHours = 6
)
$ErrorActionPreference = 'Stop'

# --- self-elevate ---------------------------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-ServiceName', $ServiceName, '-OdooService', $OdooService, '-IntervalHours', "$IntervalHours"
    )
    return
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartPs = Join-Path $ProjectRoot 'scripts\start-ai-worker.ps1'
$WorkerPy = Join-Path $ProjectRoot 'ai_worker\worker.py'
$LogDir  = Join-Path $ProjectRoot '.runtime\logs'
$PsExe   = (Get-Command powershell.exe).Source
foreach ($p in @($StartPs, $WorkerPy)) {
    if (-not (Test-Path $p)) { throw "Missing required path: $p" }
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

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
    throw "Could not obtain nssm.exe. Install it manually (winget install NSSM.NSSM) then re-run."
}
Write-Host "Using NSSM: $nssm" -ForegroundColor DarkGray

# --- idempotent re-install ------------------------------------------------
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing '$ServiceName' service for a clean re-install..." -ForegroundColor Yellow
    & $nssm stop $ServiceName confirm 2>$null | Out-Null
    & $nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

$appParams = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -IntervalHours {1}' -f $StartPs, $IntervalHours

& $nssm install $ServiceName $PsExe | Out-Null
& $nssm set $ServiceName AppParameters $appParams        | Out-Null
& $nssm set $ServiceName AppDirectory  $ProjectRoot      | Out-Null
& $nssm set $ServiceName DisplayName   "Odoo WMS AI Forecast Worker" | Out-Null
& $nssm set $ServiceName Description   "Optional out-of-process WMS forecast worker. MANUAL start; needs a real service account in .env. Restarts on failure." | Out-Null
# MANUAL start on purpose (placeholder creds would crash-loop on boot).
& $nssm set $ServiceName Start         SERVICE_DEMAND_START | Out-Null
& $nssm set $ServiceName AppStdout     (Join-Path $LogDir 'ai-worker-out.log') | Out-Null
& $nssm set $ServiceName AppStderr     (Join-Path $LogDir 'ai-worker-err.log') | Out-Null
& $nssm set $ServiceName AppRotateFiles 1        | Out-Null
& $nssm set $ServiceName AppRotateOnline 1       | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
# Supervision: restart on ANY exit, 10s delay, throttle crash loops.
& $nssm set $ServiceName AppExit Default Restart | Out-Null
& $nssm set $ServiceName AppRestartDelay 10000   | Out-Null
& $nssm set $ServiceName AppThrottle 10000       | Out-Null
& $nssm set $ServiceName AppStopMethodConsole 15000 | Out-Null
# Start only after Odoo is up (XML-RPC target).
if (Get-Service $OdooService -ErrorAction SilentlyContinue) {
    & $nssm set $ServiceName DependOnService $OdooService | Out-Null
}
& sc.exe failure $ServiceName reset= 86400 actions= restart/10000/restart/10000/restart/60000 | Out-Null
& sc.exe failureflag $ServiceName 1 | Out-Null

Write-Host ""
Write-Host "  Service    : $ServiceName  (MANUAL start)" -ForegroundColor White
Write-Host "  Supervisor : NSSM restart on exit + sc.exe failure actions" -ForegroundColor White
Write-Host "  Logs       : $LogDir\ai-worker-*.log" -ForegroundColor White
Write-Host ""
Write-Host "Registered (supervised, NOT started). Provision a real service account" -ForegroundColor Green
Write-Host "(ODOO_USER / ODOO_USER_PASSWORD in .env), then: Start-Service $ServiceName" -ForegroundColor Green

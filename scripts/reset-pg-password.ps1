<#
.SYNOPSIS
    Reset the PostgreSQL 'postgres' superuser password to a known value.

.DESCRIPTION
    Standard recovery procedure when you've forgotten the postgres password:
    1. Backup pg_hba.conf
    2. Switch local connections to 'trust' (no password needed)
    3. Restart Postgres
    4. Connect as postgres, run ALTER USER ... PASSWORD
    5. Restore pg_hba.conf
    6. Restart Postgres again

    Sets the password to whatever -NewPassword you pass (default:
    'odoo_local_dev_pw' to match the project's .env file).

    Requires Administrator rights to edit pg_hba.conf and restart the
    service. If you run this without admin, it self-elevates via UAC.

.PARAMETER NewPassword
    The new password for the 'postgres' superuser. Default:
    'odoo_local_dev_pw' (matches .env DB_PASSWORD).

.PARAMETER PgDataDir
    Path to the Postgres data directory. Default: auto-detect.

.EXAMPLE
    scripts\reset-pg-password.ps1

.EXAMPLE
    scripts\reset-pg-password.ps1 -NewPassword 'my_new_secret'
#>
[CmdletBinding()]
param(
    [string]$NewPassword = 'odoo_local_dev_pw',
    [string]$PgDataDir
)

$ErrorActionPreference = 'Stop'

# Self-elevate if not already admin.
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host "Re-launching with Administrator privileges (UAC prompt)..." -ForegroundColor Cyan
    $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$PSCommandPath,
                 '-NewPassword', $NewPassword)
    if ($PgDataDir) { $argList += @('-PgDataDir', $PgDataDir) }
    # Keep window open after script ends so user sees the output.
    $argList = @('-NoExit') + $argList
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList
    exit 0
}

Write-Host "=== Postgres password reset ===" -ForegroundColor Cyan
Write-Host ""

# Auto-detect data dir if not supplied.
if (-not $PgDataDir) {
    $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL\*\data' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $candidate) {
        throw "Cannot find Postgres data dir under C:\Program Files\PostgreSQL\*\data. Pass -PgDataDir explicitly."
    }
    $PgDataDir = $candidate.FullName
}
Write-Host "Postgres data dir: $PgDataDir" -ForegroundColor Gray

$hbaPath = Join-Path $PgDataDir 'pg_hba.conf'
$hbaBackup = "$hbaPath.bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
if (-not (Test-Path $hbaPath)) {
    throw "pg_hba.conf not found at $hbaPath"
}

# Detect the postgres service name.
$pgService = Get-Service -Name 'postgresql-x64-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $pgService) {
    throw "No postgresql-x64-* service found."
}
Write-Host "Service:           $($pgService.Name)" -ForegroundColor Gray

# Locate psql.exe relative to the service path.
$serviceBin = (Get-CimInstance Win32_Service -Filter "Name='$($pgService.Name)'").PathName
$pgBinDir = ($serviceBin -split '"' | Where-Object { $_ -match 'pg_ctl\.exe$' }) -replace 'pg_ctl\.exe$',''
$psqlExe = Join-Path $pgBinDir 'psql.exe'
if (-not (Test-Path $psqlExe)) {
    throw "psql.exe not found at $psqlExe"
}
Write-Host "psql.exe:          $psqlExe" -ForegroundColor Gray

# Read port from postgresql.conf for the connection.
$confPath = Join-Path $PgDataDir 'postgresql.conf'
$portMatch = Select-String -Path $confPath -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
$DbPort = if ($portMatch) { [int]$portMatch.Matches.Groups[1].Value } else { 5432 }
Write-Host "Port:              $DbPort" -ForegroundColor Gray
Write-Host ""

# 1. Backup
Write-Host "[1/6] Backing up pg_hba.conf -> $hbaBackup" -ForegroundColor Cyan
Copy-Item $hbaPath $hbaBackup

# 2. Trust mode
Write-Host "[2/6] Switching all local auth methods to 'trust' (temporary)" -ForegroundColor Cyan
$trustHba = @"
# Temporary trust mode for password reset.
# This file is restored from $hbaBackup at the end of reset-pg-password.ps1.
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
"@
Set-Content -Path $hbaPath -Value $trustHba -Encoding ascii

# 3. Restart
Write-Host "[3/6] Restarting $($pgService.Name)" -ForegroundColor Cyan
Restart-Service $pgService.Name
Start-Sleep -Seconds 3   # let postmaster bind the port

# 4. Set password
Write-Host "[4/6] Setting postgres password" -ForegroundColor Cyan
$escaped = $NewPassword -replace "'", "''"
& $psqlExe -U postgres -h localhost -p $DbPort -d postgres -c "ALTER USER postgres WITH PASSWORD '$escaped';"
if ($LASTEXITCODE -ne 0) { throw "ALTER USER failed (exit $LASTEXITCODE)" }
Write-Host "    Password set" -ForegroundColor Green

# 5. Restore
Write-Host "[5/6] Restoring pg_hba.conf from backup" -ForegroundColor Cyan
Copy-Item $hbaBackup $hbaPath -Force

# 6. Restart again so scram-sha-256 is back in force
Write-Host "[6/6] Restarting $($pgService.Name) (scram-sha-256 restored)" -ForegroundColor Cyan
Restart-Service $pgService.Name
Start-Sleep -Seconds 3

# Verify
$env:PGPASSWORD = $NewPassword
$check = & $psqlExe -U postgres -h localhost -p $DbPort -d postgres -tAc "SELECT 'ok';" 2>&1
if ($check -match 'ok') {
    Write-Host ""
    Write-Host "=== SUCCESS ===" -ForegroundColor Green
    Write-Host "Postgres password is now: $NewPassword" -ForegroundColor Green
    Write-Host "Port:                     $DbPort" -ForegroundColor Green
    Write-Host ""
    Write-Host "Set it at User scope so install-native.ps1 can pick it up:" -ForegroundColor Yellow
    Write-Host "    [Environment]::SetEnvironmentVariable('PGPASSWORD', '$NewPassword', 'User')" -ForegroundColor White
    Write-Host ""
    Write-Host "Backup of original pg_hba.conf left at:" -ForegroundColor Yellow
    Write-Host "    $hbaBackup" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "=== VERIFY FAILED ===" -ForegroundColor Red
    Write-Host $check -ForegroundColor Red
    Write-Host "Original pg_hba.conf is still at $hbaBackup if you need to restore manually." -ForegroundColor Yellow
}

#Requires -Version 5.1
<#
.SYNOPSIS
    Generate and set STRONG, UNIQUE passwords for Odoo login users (production
    provisioning).

.DESCRIPTION
    Production hardening helper. For each targeted internal (non-portal) user it
    generates a fresh 20-character cryptographically-random password, writes it
    to the user record via the Odoo ORM (properly hashed by Odoo), and prints
    the new credential to YOUR console exactly once.

    The passwords are generated *inside* the Odoo shell using Python's `secrets`
    module and are NEVER written to disk, a log, or anywhere persistent. Copy
    them into your password manager / sealed envelope the moment they appear,
    then close the terminal.

    Run this once before go-live to replace any default/dev passwords, and again
    whenever you add a new real user (target just that login with -Users).

.PARAMETER Users
    Comma-separated logins to (re)set, e.g. "admin,storekeeper". When omitted,
    EVERY active internal user is reset — convenient for first provisioning,
    but note it will lock out anyone whose new password you do not capture.

.PARAMETER DbName
    Target database. Defaults to 'wms'.

.PARAMETER Force
    Skip the interactive confirmation prompt.

.EXAMPLE
    .\scripts\set-user-passwords.ps1 -Users "admin,storekeeper"
    Reset just those two accounts.

.EXAMPLE
    .\scripts\set-user-passwords.ps1
    Reset every active internal user (first-provisioning mode).

.NOTES
    The running Odoo server keeps serving during this; existing browser sessions
    stay logged in (cookie-based) until they sign out, but the NEW password is
    required for the next fresh login.
#>
[CmdletBinding()]
param(
    [string]$Users = '',
    [string]$DbName = 'wms',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OdooSrc     = Join-Path $ProjectRoot '.odoo'
$VenvPy      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OdooBin     = Join-Path $OdooSrc 'odoo-bin'
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'

foreach ($p in @($VenvPy, $OdooBin, $ConfPath)) {
    if (-not (Test-Path $p)) {
        Write-Host "Required path not found: $p" -ForegroundColor Red
        Write-Host "Run scripts\install-native.ps1 first." -ForegroundColor Yellow
        exit 1
    }
}

$target = ($Users -split ',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$scope  = if ($target) { $target -join ', ' } else { 'ALL active internal users' }

Write-Host ""
Write-Host "  Set strong unique passwords  (db=$DbName)" -ForegroundColor Cyan
Write-Host "  Target: $scope" -ForegroundColor Gray
Write-Host "  The new passwords print once below. Capture them immediately." -ForegroundColor Yellow
Write-Host ""

if (-not $Force) {
    $ans = Read-Host "  This RESETS the listed users' passwords. Continue? (yes/no)"
    if ($ans -notin @('y', 'yes')) { Write-Host "  Aborted." -ForegroundColor DarkYellow; exit 0 }
}

# Python executed inside the Odoo shell. Passwords are generated here with the
# `secrets` CSPRNG and never leave this process except as console output.
$pyTemplate = @'
import secrets, string
_target = [s.strip() for s in "__USERS__".split(",") if s.strip()]
_users = env["res.users"].search([("share", "=", False), ("active", "=", True)])
if _target:
    _users = _users.filtered(lambda u: u.login in _target)
_ambiguous = set("Il1O0o")
_pool = "".join(c for c in (string.ascii_letters + string.digits + "!@#$%*-_=+") if c not in _ambiguous)
print("WMSPWD_BEGIN")
for _u in _users.sorted("login"):
    _pwd = "".join(secrets.choice(_pool) for _ in range(20))
    _u.write({"password": _pwd})
    print("WMSPWD\t%s\t%s" % (_u.login, _pwd))
env.cr.commit()
print("WMSPWD_END\t%d" % len(_users))
'@

$py = $pyTemplate -replace '__USERS__', ($target -join ',')

$tmpPy  = Join-Path $env:TEMP ("wms_setpw_{0}.py" -f $PID)
$tmpLog = Join-Path $env:TEMP ("wms_setpw_{0}.log" -f $PID)
# Write UTF-8 with NO BOM so the Odoo shell parses the first line cleanly.
[System.IO.File]::WriteAllText($tmpPy, $py, (New-Object System.Text.UTF8Encoding($false)))

try {
    # cmd /c gives us real stdin redirection (PowerShell lacks `<`); Odoo logs go
    # to a temp logfile so they don't mix with our credential output on stdout.
    $line = '"{0}" "{1}" shell -c "{2}" -d {3} --no-http --logfile="{4}" --log-level=error < "{5}"' -f `
        $VenvPy, $OdooBin, $ConfPath, $DbName, $tmpLog, $tmpPy
    $out = cmd /c $line

    $rows = @()
    foreach ($l in $out) {
        if ($l -match '^WMSPWD\t(.+)\t(.+)$') {
            $rows += [pscustomobject]@{ Login = $matches[1]; 'New Password' = $matches[2] }
        }
    }

    if (-not $rows) {
        Write-Host "  No users matched / no output. Check $tmpLog for errors." -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "  ====================  RECORD THESE NOW  ====================" -ForegroundColor Green
    $rows | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host "  ============================================================" -ForegroundColor Green
    Write-Host "  $($rows.Count) user(s) updated. Passwords are NOT stored anywhere." -ForegroundColor Gray
    Write-Host "  Store them in your password manager, then clear your terminal." -ForegroundColor Yellow
    Write-Host ""
}
finally {
    Remove-Item $tmpPy  -Force -ErrorAction SilentlyContinue
    Remove-Item $tmpLog -Force -ErrorAction SilentlyContinue
}

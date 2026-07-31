<#
.SYNOPSIS
    One-time Google Drive consent for WMS backups - mints and stores the
    OAuth refresh token that backup-native.ps1 uses for Stage-5 uploads.

.DESCRIPTION
    Runs the OAuth 2.0 Desktop-app loopback flow (127.0.0.1 + PKCE S256,
    scope drive.file only) against the OAuth client YOU created in Google
    Cloud Console, then stores the refresh token DPAPI(LocalMachine)-
    encrypted at config\gdrive-token.json.dpapi so the SYSTEM-principal
    scheduled backup task can read it.

    Run this INTERACTIVELY as the operator (it opens a browser). Do NOT
    run it as SYSTEM. Re-running replaces the stored token (idempotent).

    Prerequisites (full walkthrough: docs\22-gdrive-backup.md):
      1. Google Cloud project with the Google Drive API enabled.
      2. OAuth consent screen: External + publishing status "In production".
      3. Desktop-app OAuth client; id/secret in .env as
         GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET.

    IMPORTANT: set the OAuth consent screen publishing status to
    "In production" or Google revokes the refresh token every 7 days.
    Publishing needs NO verification review for the drive.file scope.

.PARAMETER Status
    Print the stored token's account/age/expiry, exercise it against the
    Drive API, and report GREEN/RED. No browser involved.

.PARAMETER Revoke
    Revoke the refresh token at Google and delete the local token file.

.PARAMETER EnvPath
    Override the .env path. Default: <project>\.env.

.PARAMETER TokenPath
    Override the token file path. Default: <project>\config\gdrive-token.json.dpapi.

.EXAMPLE
    scripts\setup-gdrive-auth.ps1
    # First-time consent: opens the browser, stores the token, smoke-tests.

.EXAMPLE
    scripts\setup-gdrive-auth.ps1 -Status

.EXAMPLE
    scripts\setup-gdrive-auth.ps1 -Revoke

.NOTES
    Requires: scripts\gdrive-lib.ps1 beside this script, a default browser,
              outbound HTTPS. psql is optional (quota cache is failure-safe).
    Token storage rationale (DPAPI machine scope) is documented in
    docs\22-gdrive-backup.md and SECURITY.md.
#>
[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Revoke,
    [string]$EnvPath,
    [string]$TokenPath
)

$ErrorActionPreference = 'Stop'
# PS 5.1 defaults to TLS 1.0 for .NET HTTP clients; Google endpoints require 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'
if (-not $EnvPath)   { $EnvPath   = Join-Path $ProjectRoot '.env' }
if (-not $TokenPath) { $TokenPath = Join-Path $ProjectRoot 'config\gdrive-token.json.dpapi' }

$GdLib = Join-Path $PSScriptRoot 'gdrive-lib.ps1'
if (-not (Test-Path -LiteralPath $GdLib)) {
    Write-Host "gdrive-lib.ps1 not found at $GdLib - the Drive library ships beside this script." -ForegroundColor Red
    exit 1
}
. $GdLib

# The loopback flow needs an interactive desktop session for the browser;
# the token must be minted by a human anyway (Google consent screen).
if ([Security.Principal.WindowsIdentity]::GetCurrent().IsSystem) {
    Write-Host "This script must run as the operator, NOT as SYSTEM (it opens a browser)." -ForegroundColor Red
    exit 1
}

# --- Small helpers --------------------------------------------------------

function Read-EnvKey {
    # House per-key .env read. Empty string when missing/blank.
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $m = Select-String -Path $Path -Pattern "^$Key=(.+)$" | Select-Object -First 1
    if ($m) { return $m.Matches.Groups[1].Value.Trim() }
    return ''
}

function Test-PlaceholderValue {
    # Conservative subset of install-native.ps1's placeholder set.
    param([string]$Value)
    if (-not $Value) { return $true }
    return [bool]($Value -match '^(changeme|your[_-]|example|placeholder|<.*>$)')
}

function Set-DotEnvKey {
    # Save-DotEnv-style single-key write: replace the key's line in place
    # when present (even if blank), else append. Everything else passes
    # through verbatim; UTF-8 without BOM like install-native.ps1.
    param([string]$Path, [string]$Key, [string]$Value)
    $nl = [Environment]::NewLine
    if (Test-Path -LiteralPath $Path) {
        $lines = @(Get-Content -LiteralPath $Path -Encoding utf8)
        $replaced = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match ('^\s*' + [regex]::Escape($Key) + '\s*=')) {
                $lines[$i] = "$Key=$Value"
                $replaced = $true
                break
            }
        }
        if (-not $replaced) { $lines += "$Key=$Value" }
        [System.IO.File]::WriteAllText($Path, (($lines -join $nl) + $nl), [System.Text.UTF8Encoding]::new($false))
    } else {
        [System.IO.File]::WriteAllText($Path, "$Key=$Value$nl", [System.Text.UTF8Encoding]::new($false))
    }
}

function ConvertTo-Base64Url {
    param([byte[]]$Bytes)
    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-TokenField {
    # StrictMode-safe property read on the decrypted token object.
    param($Token, [string]$Name)
    if ($Token -and $Token.PSObject.Properties[$Name]) { return [string]$Token.$Name }
    return ''
}

function ConvertTo-AboutSummary {
    # about.get returns user.emailAddress + storageQuota.{usage,limit} as
    # strings of bytes; limit is ABSENT on unlimited plans. Guarded reads.
    param($About)
    $email = ''; $usedMb = $null; $limitMb = $null
    if ($About) {
        $p = $About.PSObject.Properties
        if ($p['user'] -and $About.user -and $About.user.PSObject.Properties['emailAddress']) {
            $email = [string]$About.user.emailAddress
        }
        if ($p['storageQuota'] -and $About.storageQuota) {
            $q  = $About.storageQuota
            $qp = $q.PSObject.Properties
            if ($qp['usage'] -and "$($q.usage)" -ne '') { $usedMb  = [math]::Round([double]$q.usage / 1MB, 1) }
            if ($qp['limit'] -and "$($q.limit)" -ne '') { $limitMb = [math]::Round([double]$q.limit / 1MB, 1) }
        }
    }
    return [pscustomobject]@{ Email = $email; UsedMb = $usedMb; LimitMb = $limitMb }
}

function Format-StorageLine {
    param($Summary)
    if ($null -eq $Summary.UsedMb) { return 'storage usage not reported' }
    $used = [math]::Round($Summary.UsedMb / 1024, 2)
    if ($null -eq $Summary.LimitMb) { return "$used GB used (no fixed limit reported)" }
    $limit = [math]::Round($Summary.LimitMb / 1024, 2)
    return "$used GB used of $limit GB"
}

function Get-HttpErrorBody {
    # PS 5.1 Invoke-RestMethod throws WebException on 4xx/5xx; the JSON
    # error body (e.g. invalid_grant detail) is on the response stream.
    param($ErrorRecord)
    try {
        if ($ErrorRecord.Exception.Response) {
            $stream = $ErrorRecord.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            return $body
        }
    } catch {}
    return ''
}

# DB connection for the failure-safe quota cache (clone of backup-native).
$DbName = 'wms'; $DbHost = ''; $DbPort = 0; $DbUser = ''
if (Test-Path -LiteralPath $ConfPath) {
    $m = Select-String -Path $ConfPath -Pattern '^db_host\s*=\s*(.+)$' | Select-Object -First 1
    if ($m) { $DbHost = $m.Matches.Groups[1].Value.Trim() }
    $m = Select-String -Path $ConfPath -Pattern '^db_port\s*=\s*(\d+)$' | Select-Object -First 1
    if ($m) { $DbPort = [int]$m.Matches.Groups[1].Value }
    $m = Select-String -Path $ConfPath -Pattern '^db_user\s*=\s*(.+)$' | Select-Object -First 1
    if ($m) { $DbUser = $m.Matches.Groups[1].Value.Trim() }
    if (-not $env:PGPASSWORD) {
        $m = Select-String -Path $ConfPath -Pattern '^db_password\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $env:PGPASSWORD = $m.Matches.Groups[1].Value.Trim() }
    }
}
if (-not $DbHost) { $DbHost = 'localhost' }
if (-not $DbPort) { $DbPort = 5432 }
if (-not $DbUser) { $DbUser = 'odoo' }

function Write-GDriveLastAbout {
    # Cache {used_mb,limit_mb,checked_utc,email} to ir.config_parameter
    # wms_gdrive.last_about. FAILURE-SAFE: a missing DB / psql must never
    # fail the consent flow (Write-BackupAudit pattern).
    param($Summary)
    try {
        $payload = [ordered]@{
            used_mb     = $Summary.UsedMb
            limit_mb    = $Summary.LimitMb
            checked_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
            email       = $Summary.Email
        }
        $json = (ConvertTo-Json -InputObject $payload -Compress) -replace "'", "''"
        $sql = "INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) VALUES ('wms_gdrive.last_about', '$json', 1, NOW(), 1, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_uid = 1, write_date = NOW();"
        $sql | & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [audit] cached Drive quota in wms_gdrive.last_about" -ForegroundColor DarkGray
        } else {
            Write-Host "    [warn] quota cache not written (is the wms DB up?)" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] quota cache write failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Write-SevenDayWarning {
    # F6: Testing-status consent screens get refresh tokens that expire in
    # 7 days. Not detectable via the API, so warn unconditionally.
    Write-Host ""
    Write-Host "  REMINDER - the 7-day token trap:" -ForegroundColor Yellow
    Write-Host "  IMPORTANT: set the OAuth consent screen publishing status to" -ForegroundColor Yellow
    Write-Host "  'In production' or Google revokes the refresh token every 7 days" -ForegroundColor Yellow
    Write-Host "  and uploads silently stop. Publishing needs NO verification review" -ForegroundColor Yellow
    Write-Host "  for the drive.file scope:" -ForegroundColor Yellow
    Write-Host "      console.cloud.google.com > APIs & Services > OAuth consent screen" -ForegroundColor Yellow
}

# --- -Status: report token health, no browser -----------------------------

if ($Status) {
    Write-Host "Google Drive auth status" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $TokenPath)) {
        Write-Host "  No token stored ($TokenPath)." -ForegroundColor Red
        Write-Host "  Run scripts\setup-gdrive-auth.ps1 to connect Google Drive." -ForegroundColor Yellow
        exit 1
    }
    $tok = Read-GDriveToken -TokenPath $TokenPath
    if (-not $tok) {
        Write-Host "  Token file exists but could not be decrypted (DPAPI is machine-bound;" -ForegroundColor Red
        Write-Host "  a token file copied from another machine is unreadable). Re-run setup." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  Token file    : $TokenPath"
    Write-Host "  Account       : $(Get-TokenField $tok 'account_hint')"
    Write-Host "  Minted (UTC)  : $(Get-TokenField $tok 'minted_utc')"
    Write-Host "  Access expiry : $(Get-TokenField $tok 'expires_at_utc') (cached access token)"
    try {
        $cfg = Get-GDriveEnvConfig -EnvPath $EnvPath
        # Get-GDriveAccessToken refreshes when needed; about.get proves the
        # token is live against the API either way.
        $at  = Get-GDriveAccessToken -TokenPath $TokenPath -EnvConfig $cfg
        $sum = ConvertTo-AboutSummary (Get-GDriveAbout -AccessToken $at)
        Write-Host "  [OK] Drive auth is healthy - connected as $($sum.Email), $(Format-StorageLine $sum)." -ForegroundColor Green
        exit 0
    } catch {
        $msg = $_.Exception.Message
        Write-Host "  [FAIL] $msg" -ForegroundColor Red
        if ($msg -match 'GDRIVE_AUTH_EXPIRED|invalid_grant') {
            $ageDays = $null
            $minted = Get-TokenField $tok 'minted_utc'
            if ($minted) {
                try {
                    $mintedUtc = [datetime]::Parse($minted, [Globalization.CultureInfo]::InvariantCulture,
                        [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal)
                    $ageDays = [math]::Round(((Get-Date).ToUniversalTime() - $mintedUtc).TotalDays, 1)
                } catch {}
            }
            if ($null -ne $ageDays -and $ageDays -ge 6) {
                Write-Host ""
                Write-Host "  This token was minted $ageDays days ago and Google now rejects it" -ForegroundColor Red
                Write-Host "  (invalid_grant) - the classic 7-day expiry of a consent screen still" -ForegroundColor Red
                Write-Host "  in 'Testing' status." -ForegroundColor Red
            }
            Write-SevenDayWarning
            Write-Host ""
            Write-Host "  Then re-run scripts\setup-gdrive-auth.ps1 to mint a fresh token." -ForegroundColor Yellow
        }
        exit 1
    }
}

# --- -Revoke: invalidate at Google + delete the local file ----------------

if ($Revoke) {
    Write-Host "Revoking Google Drive access" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $TokenPath)) {
        Write-Host "  No token stored ($TokenPath) - nothing to revoke." -ForegroundColor DarkGray
        exit 0
    }
    $tok = Read-GDriveToken -TokenPath $TokenPath
    $rt = Get-TokenField $tok 'refresh_token'
    if ($rt) {
        try {
            Invoke-RestMethod -Method Post -Uri 'https://oauth2.googleapis.com/revoke' `
                -Body @{ token = $rt } -ContentType 'application/x-www-form-urlencoded' | Out-Null
            Write-Host "  [OK] Token revoked at Google." -ForegroundColor Green
        } catch {
            # 400 here usually means the token was already revoked/expired.
            Write-Host "  [warn] Google revoke endpoint rejected the token (may already be revoked): $($_.Exception.Message)" -ForegroundColor Yellow
        }
        $rt = $null
    } else {
        Write-Host "  [warn] Token file held no refresh token (corrupt?); deleting it anyway." -ForegroundColor Yellow
    }
    Remove-Item -LiteralPath $TokenPath -Force
    Write-Host "  [OK] Deleted $TokenPath - Drive uploads are now disabled." -ForegroundColor Green
    Write-Host "  You can also confirm at myaccount.google.com > Security > Third-party access." -ForegroundColor DarkGray
    exit 0
}

# --- Main consent flow -----------------------------------------------------

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " WMS Google Drive backup - one-time consent" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Prerequisites (Google Cloud Console - console.cloud.google.com):"
Write-Host "  1. Create (or pick) a project."
Write-Host "  2. APIs & Services > Library > enable 'Google Drive API'."
Write-Host "  3. APIs & Services > OAuth consent screen: User type 'External',"
Write-Host "     publishing status: 'In production'" -ForegroundColor Yellow
Write-Host "  4. Credentials > Create credentials > OAuth client ID > 'Desktop app'."
Write-Host "  5. Put the client id/secret into .env:"
Write-Host "         GDRIVE_CLIENT_ID=..." -ForegroundColor DarkGray
Write-Host "         GDRIVE_CLIENT_SECRET=..." -ForegroundColor DarkGray
Write-Host "Full walkthrough: docs\22-gdrive-backup.md"
Write-SevenDayWarning
Write-Host ""

# Step 2: client id/secret from .env (house per-key Select-String idiom).
$ClientId     = Read-EnvKey -Path $EnvPath -Key 'GDRIVE_CLIENT_ID'
$ClientSecret = Read-EnvKey -Path $EnvPath -Key 'GDRIVE_CLIENT_SECRET'
if (Test-PlaceholderValue $ClientId)     { $ClientId = '' }
if (Test-PlaceholderValue $ClientSecret) { $ClientSecret = '' }

if (-not $ClientId -or -not $ClientSecret) {
    Write-Host "GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET are not set in .env ($EnvPath)." -ForegroundColor Red
    Write-Host "Create a Desktop-app OAuth client first - see the setup section of" -ForegroundColor Yellow
    Write-Host "docs\22-gdrive-backup.md - then either edit .env or paste the values now." -ForegroundColor Yellow
    Write-Host ""
    $enteredId = Read-Host "Paste the OAuth client ID now (or press Enter to abort)"
    $enteredId = "$enteredId".Trim()
    if (-not $enteredId) {
        Write-Host "Aborted. Add the keys to .env and re-run." -ForegroundColor Red
        exit 1
    }
    $enteredSecret = "$(Read-Host 'Paste the OAuth client secret')".Trim()
    if (-not $enteredSecret) {
        Write-Host "No client secret entered - aborting." -ForegroundColor Red
        exit 1
    }
    # The scheduled backup refreshes tokens with these values, so they MUST
    # live in .env - consent to write it or the feature cannot run.
    $save = Read-Host "Save both to .env so the nightly backup can refresh tokens? (Y/n)"
    if ($save -and $save -notmatch '^[Yy]') {
        Write-Host "Aborted: the backup pipeline reads these keys from .env at every run." -ForegroundColor Red
        exit 1
    }
    if (Test-Path -LiteralPath $EnvPath) {
        $bak = "$EnvPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item -LiteralPath $EnvPath -Destination $bak -Force
        Write-Host "    [bak] .env preserved at $bak" -ForegroundColor DarkGray
    }
    Set-DotEnvKey -Path $EnvPath -Key 'GDRIVE_CLIENT_ID' -Value $enteredId
    Set-DotEnvKey -Path $EnvPath -Key 'GDRIVE_CLIENT_SECRET' -Value $enteredSecret
    Write-Host "    [OK] Wrote GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET to .env." -ForegroundColor Green
    $ClientId = $enteredId
    $ClientSecret = $enteredSecret
}
if ($ClientId -notmatch '\.apps\.googleusercontent\.com$') {
    Write-Host "    [warn] GDRIVE_CLIENT_ID does not look like a Google OAuth client id (*.apps.googleusercontent.com)." -ForegroundColor Yellow
}

# Canonical config read (validates placeholders, carries ParentFolderId).
$EnvConfig = Get-GDriveEnvConfig -EnvPath $EnvPath

if (Test-Path -LiteralPath $TokenPath) {
    Write-Host "A token is already stored - completing this flow REPLACES it." -ForegroundColor Yellow
}

# Step 3: PKCE verifier/challenge + CSRF state (CSPRNG; PS 5.1-safe).
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $vBytes = New-Object byte[] 64      # 64 bytes -> 86-char base64url (43-128 allowed)
    $rng.GetBytes($vBytes)
    $sBytes = New-Object byte[] 16
    $rng.GetBytes($sBytes)
} finally {
    $rng.Dispose()
}
$CodeVerifier = ConvertTo-Base64Url $vBytes
$State        = ConvertTo-Base64Url $sBytes
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $CodeChallenge = ConvertTo-Base64Url ($sha.ComputeHash([System.Text.Encoding]::ASCII.GetBytes($CodeVerifier)))
} finally {
    $sha.Dispose()
}

# Step 3b: loopback listener on a random free port (F8: OOB flow is dead;
# 127.0.0.1 HttpListener needs no URL ACL / elevation).
$Http = $null
$Port = 0
foreach ($attempt in 1..20) {
    $tryPort = Get-Random -Minimum 49152 -Maximum 65500
    $cand = New-Object System.Net.HttpListener
    $cand.Prefixes.Add("http://127.0.0.1:$tryPort/")
    try {
        $cand.Start()
        $Http = $cand
        $Port = $tryPort
        break
    } catch {
        $cand.Close()
    }
}
if (-not $Http) {
    Write-Host "Could not bind a loopback port for the OAuth redirect (tried 20 random ports)." -ForegroundColor Red
    exit 1
}
$RedirectUri = "http://127.0.0.1:$Port"

# Step 4: open the browser at the consent URL.
$authParams = @(
    "client_id=$([Uri]::EscapeDataString($ClientId))"
    "redirect_uri=$([Uri]::EscapeDataString($RedirectUri))"
    'response_type=code'
    "scope=$([Uri]::EscapeDataString('https://www.googleapis.com/auth/drive.file'))"
    'access_type=offline'
    'prompt=consent'
    "state=$State"
    "code_challenge=$CodeChallenge"
    'code_challenge_method=S256'
)
$AuthUrl = 'https://accounts.google.com/o/oauth2/v2/auth?' + ($authParams -join '&')

$Code = $null
try {
    Write-Host "Opening your browser for Google consent (listening on $RedirectUri)..." -ForegroundColor Cyan
    Write-Host "    Sign in with the Gmail account that will own the backups and click Allow."
    Write-Host "    If no browser opens, paste this URL into one manually:" -ForegroundColor DarkGray
    Write-Host "    $AuthUrl" -ForegroundColor DarkGray
    Start-Process $AuthUrl

    # Step 5: wait for the redirect (5-minute budget). Browsers may probe
    # for /favicon.ico first, so loop until a request carries code/error.
    $deadline = (Get-Date).AddMinutes(5)
    $oauthError = $null
    while (-not $Code -and -not $oauthError) {
        $remainingMs = [int]([math]::Max(0, ($deadline - (Get-Date)).TotalMilliseconds))
        if ($remainingMs -le 0) {
            throw "Timed out after 5 minutes waiting for the browser consent. Re-run and complete the consent promptly."
        }
        $ctxTask = $Http.GetContextAsync()
        if (-not $ctxTask.Wait($remainingMs)) {
            throw "Timed out after 5 minutes waiting for the browser consent. Re-run and complete the consent promptly."
        }
        $ctx = $ctxTask.Result
        $qs = $ctx.Request.QueryString
        $gotCode  = $qs['code']
        $gotError = $qs['error']
        $gotState = $qs['state']
        if (-not $gotCode -and -not $gotError) {
            # favicon / stray probe: 404 and keep listening.
            $ctx.Response.StatusCode = 404
            $ctx.Response.Close()
            continue
        }
        $html = if ($gotCode) {
            '<html><body style="font-family:sans-serif"><h3>WMS backup is connected.</h3><p>You can close this tab and return to the PowerShell window.</p></body></html>'
        } else {
            '<html><body style="font-family:sans-serif"><h3>Consent was not granted.</h3><p>Close this tab and check the PowerShell window.</p></body></html>'
        }
        $buf = [System.Text.Encoding]::UTF8.GetBytes($html)
        $ctx.Response.ContentType = 'text/html'
        $ctx.Response.ContentLength64 = $buf.Length
        $ctx.Response.OutputStream.Write($buf, 0, $buf.Length)
        $ctx.Response.OutputStream.Close()
        if ($gotError) { $oauthError = $gotError; break }
        if ($gotState -ne $State) {
            throw "State mismatch in the OAuth redirect (possible interception) - aborting. Re-run setup."
        }
        $Code = $gotCode
    }
    if ($oauthError) {
        throw "Google returned an error during consent: $oauthError"
    }
} finally {
    if ($Http) {
        try { $Http.Stop() } catch {}
        $Http.Close()
    }
}
Write-Host "    [OK] Authorization code received." -ForegroundColor Green

# Step 6: exchange the code for tokens (PKCE verifier proves possession).
$TokenResp = $null
try {
    $TokenResp = Invoke-RestMethod -Method Post -Uri 'https://oauth2.googleapis.com/token' `
        -ContentType 'application/x-www-form-urlencoded' -Body @{
            code          = $Code
            client_id     = $ClientId
            client_secret = $ClientSecret
            redirect_uri  = $RedirectUri
            grant_type    = 'authorization_code'
            code_verifier = $CodeVerifier
        }
} catch {
    $detail = Get-HttpErrorBody $_
    Write-Host "Token exchange failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($detail) { Write-Host "    $detail" -ForegroundColor DarkGray }
    Write-Host "Check that the OAuth client is type 'Desktop app' and the id/secret in .env are exact." -ForegroundColor Yellow
    exit 1
}
$Code = $null
$CodeVerifier = $null

if (-not ($TokenResp.PSObject.Properties['refresh_token'] -and $TokenResp.refresh_token)) {
    Write-Host "Google did not return a refresh token (access_type=offline&prompt=consent should force one)." -ForegroundColor Red
    Write-Host "Remove this app at myaccount.google.com > Security > Third-party access, then re-run." -ForegroundColor Yellow
    exit 1
}

$expiresIn = 3600
if ($TokenResp.PSObject.Properties['expires_in'] -and $TokenResp.expires_in) { $expiresIn = [int]$TokenResp.expires_in }
$nowUtc = (Get-Date).ToUniversalTime()
$Token = [pscustomobject]@{
    refresh_token  = [string]$TokenResp.refresh_token
    access_token   = [string]$TokenResp.access_token
    expires_at_utc = $nowUtc.AddSeconds($expiresIn - 60).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    scope          = 'https://www.googleapis.com/auth/drive.file'
    account_hint   = ''
    minted_utc     = $nowUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
}
$TokenResp = $null

# DPAPI machine scope so the SYSTEM-principal scheduled task can read it.
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TokenPath) | Out-Null
Save-GDriveToken -TokenPath $TokenPath -Token $Token
Write-Host "    [OK] Refresh token stored (DPAPI machine scope): $TokenPath" -ForegroundColor Green

# Steps 7-8: smoke test - prove the token works, create the folder tree,
# cache the quota. The token is already saved; a smoke-test failure leaves
# it in place but exits non-zero so the operator knows setup is incomplete.
try {
    $AccessToken = $Token.access_token
    $sum = ConvertTo-AboutSummary (Get-GDriveAbout -AccessToken $AccessToken)
    Write-Host ""
    Write-Host "Connected to Google Drive" -ForegroundColor Cyan
    Write-Host "    Account : $($sum.Email)" -ForegroundColor Green
    Write-Host "    Storage : $(Format-StorageLine $sum)" -ForegroundColor Green
    if ($sum.Email) {
        $Token.account_hint = $sum.Email
        Save-GDriveToken -TokenPath $TokenPath -Token $Token
    }

    $folderId = Resolve-GDriveBackupFolder -Date (Get-Date) -EnvConfig $EnvConfig -AccessToken $AccessToken
    Write-Host "    Backup folder tree ready: https://drive.google.com/drive/folders/$folderId" -ForegroundColor Green

    Write-GDriveLastAbout -Summary $sum
} catch {
    Write-Host "    [warn] Token stored, but the post-consent smoke test failed:" -ForegroundColor Yellow
    Write-Host "           $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "    Verify connectivity and re-check with: scripts\setup-gdrive-auth.ps1 -Status" -ForegroundColor Yellow
    exit 1
} finally {
    $Token = $null
    $AccessToken = $null
}

# Step 9: next steps + the 7-day warning one last time.
Write-Host ""
Write-Host "Setup complete. Next steps:" -ForegroundColor Cyan
Write-Host "  1. scripts\install-backup-tasks.ps1   (daily 4:30 PM backup + on-demand manual task)"
Write-Host "  2. In Odoo: WMS > Configuration > Google Drive Backup > Test Upload"
Write-Host "  3. Re-check anytime with: scripts\setup-gdrive-auth.ps1 -Status"
Write-SevenDayWarning

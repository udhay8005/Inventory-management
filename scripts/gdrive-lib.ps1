<#
.SYNOPSIS
    Google Drive REST library for the WMS backup pipeline (dot-sourced).

.DESCRIPTION
    Pure PowerShell 5.1 Drive API v3 client consumed by backup-native.ps1
    (Stage 5), gdrive-test.ps1, gdrive-restore.ps1 and setup-gdrive-auth.ps1.

    Covers:
      - OAuth refresh-token grant against https://oauth2.googleapis.com/token,
        with the refresh token held in a DPAPI machine-scope blob
        (config\gdrive-token.json.dpapi) so SYSTEM scheduled tasks can read it.
      - Idempotent Inventory_Backups/YYYY/MM-MonthName/YYYY-MM-DD folder ensure.
      - Uploads: multipart <= 5 MB, resumable with 8 MiB chunks above (Drive
        requires chunk sizes in multiples of 256 KiB), 308-resume handling.
      - Upload verification via files.sha256Checksum (no re-download).
      - appProperties tagging + flat query, tiered retention (daily/weekly/
        monthly) with manual/emergency exemption.
      - psql-written catalog rows (wms_gdrive_backup) and ir.config_parameter
        reads, both failure-safe: a Drive or DB hiccup must NEVER fail the
        local backup.

    No top-level side effects beyond TLS 1.2 setup and constants.
    Set-StrictMode is owned by the host scripts; every function here is
    StrictMode-safe (no reads of undefined variables or absent properties).

    MOCK SEAM: when $env:GDRIVE_MOCK_DIR is non-empty, every public function
    operates against that local directory instead of the Drive API (folders =
    subdirectories, uploads = verified copies with *.gdrivemeta.json sidecars,
    about = synthetic quota). This lets the E2E suite run the full pipeline
    without Google credentials.

.NOTES
    Dot-source from a host script:
        . (Join-Path $PSScriptRoot 'gdrive-lib.ps1')
#>

# PS 5.1 defaults .NET HTTP clients to TLS 1.0; Google endpoints require 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:GDriveApiBase         = 'https://www.googleapis.com/drive/v3'
$script:GDriveUploadBase      = 'https://www.googleapis.com/upload/drive/v3'
$script:GDriveTokenUri        = 'https://oauth2.googleapis.com/token'
$script:GDriveSimpleUploadMax = 5MB    # multipart recommended <= 5 MB (Drive docs)
$script:GDriveChunkSize       = 8MB    # resumable chunk: 32 x 256 KiB (multiple-of-256KiB rule)
# Auth context recorded by Get-GDriveAccessToken so Invoke-GDriveApi can force
# exactly one token re-refresh when an in-flight call hits a 401.
$script:GDriveAuthTokenPath   = $null
$script:GDriveAuthEnvConfig   = $null

# === Internal helpers =====================================================

function Get-GDriveProp {
    # Safe property read. Drive responses omit empty fields entirely (e.g.
    # files.list returns {} when nothing matches), and host scripts may run
    # Set-StrictMode -Version Latest, where touching an absent property throws.
    param(
        [object]$Object,
        [Parameter(Mandatory)] [string]$Name,
        [object]$Default = $null
    )
    if ($null -eq $Object) { return $Default }
    if ($Object -is [hashtable]) {
        if ($Object.ContainsKey($Name)) { return $Object[$Name] }
        return $Default
    }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -ne $p -and $null -ne $p.Value) { return $p.Value }
    return $Default
}

function ConvertTo-GDriveQueryLiteral {
    # Escape a value for embedding inside single quotes in a Drive q expression
    # (q grammar: backslash escapes, ' -> \').
    param([Parameter(Mandatory)] [string]$Value)
    return ($Value -replace '\\', '\\' -replace "'", "\'")
}

function Get-GDriveHttpStatus {
    # HTTP status code out of an Invoke-RestMethod/Invoke-WebRequest error
    # record; 0 when there was no response at all (offline / DNS / timeout).
    param([Parameter(Mandatory)] [System.Management.Automation.ErrorRecord]$ErrorRecord)
    try {
        $resp = $ErrorRecord.Exception.Response
        if ($null -ne $resp) { return [int]$resp.StatusCode }
    } catch { }
    return 0
}

function Get-GDriveHttpErrorBody {
    # Google error JSON body from a failed web call; '' when unreadable.
    # Never contains token material (Google error docs carry only the error).
    param([Parameter(Mandatory)] [System.Management.Automation.ErrorRecord]$ErrorRecord)
    try {
        $resp = $ErrorRecord.Exception.Response
        if ($null -ne $resp) {
            $stream = $resp.GetResponseStream()
            if ($null -ne $stream) {
                $reader = New-Object System.IO.StreamReader($stream)
                try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
            }
        }
    } catch { }
    return ''
}

function Get-GDriveErrorClass {
    # P14 error taxonomy. Callers use the class for messaging/decisions:
    #   offline      -> retry next run (pending sweep picks the set up)
    #   auth_expired -> re-run setup-gdrive-auth.ps1 (and publish the consent
    #                   screen to Production if it is still in Testing)
    #   quota        -> Drive storage full; retention/upgrade needed
    #   server_error -> transient; already retried with backoff
    #   client_error -> permanent config/request problem
    param(
        [int]$StatusCode = 0,
        [string]$Reason = '',
        [string]$Message = ''
    )
    if ($Message -match 'GDRIVE_AUTH_EXPIRED' -or $Reason -eq 'invalid_grant' -or $StatusCode -eq 401) {
        return 'auth_expired'
    }
    if ($Reason -eq 'storageQuotaExceeded' -or $Message -match 'storageQuotaExceeded') {
        return 'quota'
    }
    if ($StatusCode -eq 0) { return 'offline' }
    if ($StatusCode -eq 429 -or $StatusCode -ge 500) { return 'server_error' }
    if ($StatusCode -eq 403 -and ($Reason -eq 'userRateLimitExceeded' -or $Reason -eq 'rateLimitExceeded')) {
        return 'server_error'
    }
    if ($StatusCode -ge 400) { return 'client_error' }
    return 'unknown'
}

function Resolve-WmsDbConnection {
    # Mirrors backup-native.ps1's odoo.native.conf resolution so the psql
    # helpers work when the lib is used standalone (gdrive-test.ps1,
    # gdrive-restore.ps1) and not just inside backup-native's variable scope.
    # Also sets PGPASSWORD from the conf when absent (-w never prompts).
    param(
        [string]$DbName,
        [string]$DbHost,
        [int]$DbPort,
        [string]$DbUser
    )
    $confPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'config\odoo.native.conf'
    if (Test-Path -LiteralPath $confPath) {
        if (-not $DbHost) {
            $m = Select-String -Path $confPath -Pattern '^db_host\s*=\s*(.+)$' | Select-Object -First 1
            if ($m) { $DbHost = $m.Matches.Groups[1].Value.Trim() }
        }
        if (-not $DbPort) {
            $m = Select-String -Path $confPath -Pattern '^db_port\s*=\s*(\d+)$' | Select-Object -First 1
            if ($m) { $DbPort = [int]$m.Matches.Groups[1].Value }
        }
        if (-not $DbUser) {
            $m = Select-String -Path $confPath -Pattern '^db_user\s*=\s*(.+)$' | Select-Object -First 1
            if ($m) { $DbUser = $m.Matches.Groups[1].Value.Trim() }
        }
        if (-not $env:PGPASSWORD) {
            $m = Select-String -Path $confPath -Pattern '^db_password\s*=\s*(.+)$' | Select-Object -First 1
            if ($m) { $env:PGPASSWORD = $m.Matches.Groups[1].Value.Trim() }
        }
    }
    if (-not $DbName) { $DbName = 'wms' }
    if (-not $DbHost) { $DbHost = 'localhost' }
    if (-not $DbPort) { $DbPort = 5432 }
    if (-not $DbUser) { $DbUser = 'odoo' }
    return [pscustomobject]@{ DbName = $DbName; DbHost = $DbHost; DbPort = $DbPort; DbUser = $DbUser }
}

# === Mock seam ============================================================

function Test-GDriveMock {
    # $true when the filesystem-backed fake of the Drive API is active.
    return [bool]$env:GDRIVE_MOCK_DIR
}

function Get-GDriveMockRoot {
    if (-not $env:GDRIVE_MOCK_DIR) { throw 'GDRIVE_MOCK_DIR is not set' }
    if (-not (Test-Path -LiteralPath $env:GDRIVE_MOCK_DIR)) {
        New-Item -ItemType Directory -Force -Path $env:GDRIVE_MOCK_DIR | Out-Null
    }
    return (Resolve-Path -LiteralPath $env:GDRIVE_MOCK_DIR).Path
}

function Resolve-GDriveMockId {
    # In mock mode a Drive id IS a filesystem path; '' / 'root' map to the
    # mock root directory.
    param([string]$Id)
    if (-not $Id -or $Id -eq 'root') { return (Get-GDriveMockRoot) }
    return $Id
}

function Write-GDriveMockMeta {
    # Sidecar metadata file so mock uploads stay queryable by appProperties
    # (Get-GDriveBackupSets) exactly like the real API.
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [hashtable]$AppProperties,
        [Parameter(Mandatory)] [string]$Sha256
    )
    $props = @{ }
    if ($AppProperties) { $props = $AppProperties }
    $meta = [ordered]@{
        id             = $FilePath
        name           = (Split-Path -Leaf $FilePath)
        size           = "$((Get-Item -LiteralPath $FilePath).Length)"
        sha256Checksum = $Sha256.ToLowerInvariant()
        createdTime    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        appProperties  = $props
        parents        = @((Split-Path -Parent $FilePath))
    }
    ($meta | ConvertTo-Json -Depth 5) |
        Set-Content -LiteralPath "$FilePath.gdrivemeta.json" -Encoding UTF8
}

# === .env / token / access token ==========================================

function Get-GDriveEnvConfig {
    # Per-key Select-String pulls (house idiom). Blank values = feature
    # disabled; placeholder-looking values are a configuration error -> throw.
    param([Parameter(Mandatory)] [string]$EnvPath)
    $cfg = [ordered]@{ ClientId = ''; ClientSecret = ''; ParentFolderId = ''; HeartbeatUrl = '' }
    if (Test-Path -LiteralPath $EnvPath) {
        $m = Select-String -Path $EnvPath -Pattern '^GDRIVE_CLIENT_ID=(.+)$' | Select-Object -First 1
        if ($m) { $cfg.ClientId = $m.Matches.Groups[1].Value.Trim() }
        $m = Select-String -Path $EnvPath -Pattern '^GDRIVE_CLIENT_SECRET=(.+)$' | Select-Object -First 1
        if ($m) { $cfg.ClientSecret = $m.Matches.Groups[1].Value.Trim() }
        $m = Select-String -Path $EnvPath -Pattern '^GDRIVE_PARENT_FOLDER_ID=(.+)$' | Select-Object -First 1
        if ($m) { $cfg.ParentFolderId = $m.Matches.Groups[1].Value.Trim() }
        $m = Select-String -Path $EnvPath -Pattern '^HEALTHCHECK_GDRIVE_URL=(.+)$' | Select-Object -First 1
        if ($m) { $cfg.HeartbeatUrl = $m.Matches.Groups[1].Value.Trim() }
    }
    # Layer-3 placeholder check (matched values are placeholders, never real
    # secrets, so echoing them back is safe).
    foreach ($pair in @(
            @{ Key = 'GDRIVE_CLIENT_ID';     Value = $cfg.ClientId },
            @{ Key = 'GDRIVE_CLIENT_SECRET'; Value = $cfg.ClientSecret })) {
        if ($pair.Value -and $pair.Value -match '^(changeme.*|your_.+_here|<.+>|x{3,}|todo.*)$') {
            throw "$($pair.Key) in .env is still a placeholder ('$($pair.Value)') - paste the real OAuth Desktop-app value (see docs/22-gdrive-backup.md)."
        }
    }
    return [pscustomobject]$cfg
}

function Read-GDriveToken {
    # DPAPI(LocalMachine) blob -> token JSON object; $null when the file is
    # missing (= Drive feature not set up, the primary feature gate).
    param([Parameter(Mandatory)] [string]$TokenPath)
    if (-not (Test-Path -LiteralPath $TokenPath)) { return $null }
    Add-Type -AssemblyName System.Security
    $clear = $null
    try {
        $b64 = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
        try {
            $protected = [Convert]::FromBase64String($b64)
            $clear = [System.Security.Cryptography.ProtectedData]::Unprotect(
                $protected, $null,
                [System.Security.Cryptography.DataProtectionScope]::LocalMachine)
        } catch {
            throw "Google Drive token file could not be decrypted (DPAPI machine scope - was it copied from another machine?): $($_.Exception.Message). Re-run scripts\setup-gdrive-auth.ps1."
        }
        return ([System.Text.Encoding]::UTF8.GetString($clear) | ConvertFrom-Json)
    } finally {
        # Zero the plaintext byte copy; the returned object still carries the
        # refresh token because callers need it - lifetime ends with their scope.
        if ($null -ne $clear) { [Array]::Clear($clear, 0, $clear.Length) }
    }
}

function Save-GDriveToken {
    # Token JSON -> DPAPI(LocalMachine) -> Base64 file. Machine scope so the
    # SYSTEM scheduled tasks can read a token minted interactively.
    param(
        [Parameter(Mandatory)] [string]$TokenPath,
        [Parameter(Mandatory)] [object]$Token
    )
    Add-Type -AssemblyName System.Security
    $dir = Split-Path -Parent $TokenPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $bytes = $null
    try {
        $json  = $Token | ConvertTo-Json -Depth 5
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
        $protected = [System.Security.Cryptography.ProtectedData]::Protect(
            $bytes, $null,
            [System.Security.Cryptography.DataProtectionScope]::LocalMachine)
        [System.IO.File]::WriteAllText($TokenPath, [Convert]::ToBase64String($protected),
            [System.Text.Encoding]::ASCII)
    } finally {
        if ($null -ne $bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
        $json = $null
    }
}

function Get-GDriveAccessToken {
    # Returns a valid access token string, refreshing via the refresh-token
    # grant when the cached one expires within 120 s (or -ForceRefresh, used
    # by Invoke-GDriveApi's single 401 retry).
    param(
        [Parameter(Mandatory)] [string]$TokenPath,
        [Parameter(Mandatory)] [object]$EnvConfig,
        [switch]$ForceRefresh
    )
    if (Test-GDriveMock) { return 'gdrive-mock-token' }
    $tok = Read-GDriveToken -TokenPath $TokenPath
    if ($null -eq $tok) {
        throw "Google Drive token file not found at $TokenPath - run scripts\setup-gdrive-auth.ps1 first."
    }
    $script:GDriveAuthTokenPath = $TokenPath
    $script:GDriveAuthEnvConfig = $EnvConfig

    $access = [string](Get-GDriveProp $tok 'access_token' '')
    $expIso = [string](Get-GDriveProp $tok 'expires_at_utc' '')
    if (-not $ForceRefresh -and $access -and $expIso) {
        $exp = [datetime]::MinValue
        $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor `
                  [System.Globalization.DateTimeStyles]::AdjustToUniversal
        if ([datetime]::TryParse($expIso, [System.Globalization.CultureInfo]::InvariantCulture, $styles, [ref]$exp)) {
            if (($exp - (Get-Date).ToUniversalTime()).TotalSeconds -gt 120) { return $access }
        }
    }

    $refresh = [string](Get-GDriveProp $tok 'refresh_token' '')
    if (-not $refresh) {
        throw "Google Drive token file has no refresh_token - re-run scripts\setup-gdrive-auth.ps1."
    }
    if (-not $EnvConfig.ClientId -or -not $EnvConfig.ClientSecret) {
        throw 'GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET missing in .env - the refresh-token grant needs both.'
    }

    $resp = $null
    $body = ('grant_type=refresh_token&client_id={0}&client_secret={1}&refresh_token={2}' -f
        [uri]::EscapeDataString($EnvConfig.ClientId),
        [uri]::EscapeDataString($EnvConfig.ClientSecret),
        [uri]::EscapeDataString($refresh))
    try {
        $resp = Invoke-RestMethod -Method Post -Uri $script:GDriveTokenUri `
            -ContentType 'application/x-www-form-urlencoded' -Body $body -TimeoutSec 30
    } catch {
        $errBody = Get-GDriveHttpErrorBody $_
        if ($errBody -match 'invalid_grant') {
            # 7-day Testing-status expiry, 6-month inactivity, or user revocation.
            throw "GDRIVE_AUTH_EXPIRED: re-run scripts\setup-gdrive-auth.ps1 (if the GCP consent screen is still in 'Testing', publish it to Production - 7-day expiry)"
        }
        throw "Google OAuth token refresh failed: $($_.Exception.Message) $errBody"
    } finally {
        # The grant body carries client secret + refresh token; cut its lifetime.
        $body = $null
    }

    $newAccess = [string](Get-GDriveProp $resp 'access_token' '')
    if (-not $newAccess) { throw 'Google OAuth token refresh returned no access_token.' }
    $expiresIn = [int](Get-GDriveProp $resp 'expires_in' 3600)
    # Google occasionally rotates the refresh token on refresh; keep the new one.
    $newRefresh = [string](Get-GDriveProp $resp 'refresh_token' '')
    if ($newRefresh) { $refresh = $newRefresh }
    $updated = [ordered]@{
        refresh_token  = $refresh
        access_token   = $newAccess
        expires_at_utc = (Get-Date).ToUniversalTime().AddSeconds($expiresIn - 60).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        scope          = [string](Get-GDriveProp $tok 'scope' 'https://www.googleapis.com/auth/drive.file')
        account_hint   = [string](Get-GDriveProp $tok 'account_hint' '')
        minted_utc     = [string](Get-GDriveProp $tok 'minted_utc' '')
    }
    Save-GDriveToken -TokenPath $TokenPath -Token $updated
    return $newAccess
}

# === Core REST wrapper ====================================================

function Invoke-GDriveApi {
    # Invoke-RestMethod wrapper for JSON Drive calls. Retries 429/5xx/network
    # errors with 2 s/4 s/8 s backoff + 0-1000 ms jitter; 403 rate-limit
    # reasons are retried too (Drive guidance). A 401 triggers exactly one
    # forced token re-refresh + retry. Other 4xx throw immediately.
    # The Authorization header is never logged or included in error text.
    param(
        [Parameter(Mandatory)] [string]$Method,
        [Parameter(Mandatory)] [string]$Uri,
        [object]$Body,
        [hashtable]$Query,
        [string]$AccessToken,
        [int]$MaxAttempts = 3
    )
    if (Test-GDriveMock) {
        throw 'GDRIVE_MOCK_DIR is set: raw Drive API calls are unavailable in mock mode.'
    }
    $full = $Uri
    if ($full -notmatch '^https?://') { $full = "$script:GDriveApiBase/$full" }
    if ($Query -and $Query.Count -gt 0) {
        $pairs = foreach ($k in $Query.Keys) {
            '{0}={1}' -f [uri]::EscapeDataString("$k"), [uri]::EscapeDataString("$($Query[$k])")
        }
        $sep = '?'
        if ($full.Contains('?')) { $sep = '&' }
        $full = $full + $sep + ($pairs -join '&')
    }
    $reauthDone = $false
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $irm = @{
                Method     = $Method
                Uri        = $full
                TimeoutSec = 120
                Headers    = @{ Authorization = "Bearer $AccessToken" }
            }
            if ($null -ne $Body) {
                $irm['Body']        = ($Body | ConvertTo-Json -Depth 12 -Compress)
                $irm['ContentType'] = 'application/json; charset=utf-8'
            }
            return Invoke-RestMethod @irm
        } catch {
            $status  = Get-GDriveHttpStatus $_
            $errBody = Get-GDriveHttpErrorBody $_
            $reason  = ''
            $gmsg    = ''
            if ($errBody) {
                try {
                    $ej   = $errBody | ConvertFrom-Json
                    $eobj = Get-GDriveProp $ej 'error' $null
                    $gmsg = [string](Get-GDriveProp $eobj 'message' '')
                    $errs = Get-GDriveProp $eobj 'errors' $null
                    if ($errs) { $reason = [string](Get-GDriveProp (@($errs)[0]) 'reason' '') }
                } catch { }
            }
            if ($status -eq 401 -and -not $reauthDone -and
                $script:GDriveAuthTokenPath -and $null -ne $script:GDriveAuthEnvConfig) {
                $reauthDone  = $true
                $AccessToken = Get-GDriveAccessToken -TokenPath $script:GDriveAuthTokenPath `
                    -EnvConfig $script:GDriveAuthEnvConfig -ForceRefresh
                $attempt--   # the single re-auth retry does not consume a transient attempt
                continue
            }
            $transient = ($status -in 429, 500, 502, 503, 504) -or ($status -eq 0) -or
                         ($status -eq 403 -and ($reason -eq 'userRateLimitExceeded' -or $reason -eq 'rateLimitExceeded'))
            if ($transient -and $attempt -lt $MaxAttempts) {
                Start-Sleep -Milliseconds (([math]::Pow(2, $attempt) * 1000) + (Get-Random -Maximum 1000))
                continue
            }
            $class = Get-GDriveErrorClass -StatusCode $status -Reason $reason -Message $_.Exception.Message
            $reasonPart = ''
            if ($reason) { $reasonPart = "/$reason" }
            $detail = $_.Exception.Message
            if ($gmsg) { $detail = $gmsg }
            throw ('Drive API {0} {1} failed (HTTP {2}, {3}{4}): {5}' -f
                $Method.ToUpper(), $Uri, $status, $class, $reasonPart, $detail)
        }
    }
}

# === Folders ==============================================================

function Find-GDriveFolder {
    # files.list lookup of one app-visible folder by exact name under a
    # parent. Returns the folder id string, or $null when none exists.
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$ParentId,
        [string]$AccessToken
    )
    if (Test-GDriveMock) {
        $parentPath = Resolve-GDriveMockId $ParentId
        $cand = Join-Path $parentPath $Name
        if (Test-Path -LiteralPath $cand -PathType Container) { return $cand }
        return $null
    }
    $escName   = ConvertTo-GDriveQueryLiteral $Name
    $escParent = ConvertTo-GDriveQueryLiteral $ParentId
    $q = "name='$escName' and mimeType='application/vnd.google-apps.folder' and '$escParent' in parents and trashed=false"
    $res = Invoke-GDriveApi -Method Get -Uri 'files' -AccessToken $AccessToken -Query @{
        q        = $q
        fields   = 'files(id,name)'
        pageSize = '10'
        spaces   = 'drive'
    }
    $files = @(Get-GDriveProp $res 'files' @())
    if ($files.Count -gt 0) { return [string]$files[0].id }
    return $null
}

function New-GDriveFolder {
    # files.create folder; returns the new folder id.
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$ParentId,
        [string]$AccessToken
    )
    if (Test-GDriveMock) {
        $parentPath = Resolve-GDriveMockId $ParentId
        $path = Join-Path $parentPath $Name
        New-Item -ItemType Directory -Force -Path $path | Out-Null
        return $path
    }
    $res = Invoke-GDriveApi -Method Post -Uri 'files' -AccessToken $AccessToken `
        -Query @{ fields = 'id,name' } -Body @{
            name     = $Name
            mimeType = 'application/vnd.google-apps.folder'
            parents  = @($ParentId)
        }
    return [string]$res.id
}

function Resolve-GDriveBackupFolder {
    # Idempotent ensure of <parent>/<FolderName>/YYYY/MM-MonthName/YYYY-MM-DD;
    # returns the day-folder id. Month name is invariant English ("06-June")
    # so the tree never depends on the host locale. No id caching across runs
    # (4-8 calls/day is far below quota).
    param(
        [Parameter(Mandatory)] [datetime]$Date,
        [object]$EnvConfig,
        [string]$AccessToken,
        [string]$FolderName = 'Inventory_Backups'
    )
    $parent = 'root'
    if ($EnvConfig) {
        $pf = [string](Get-GDriveProp $EnvConfig 'ParentFolderId' '')
        if ($pf) { $parent = $pf }
    }
    $monthName = [System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($Date.Month)
    $segments = @(
        $FolderName,
        $Date.ToString('yyyy'),
        ('{0:00}-{1}' -f $Date.Month, $monthName),
        $Date.ToString('yyyy-MM-dd')
    )
    foreach ($segment in $segments) {
        $id = Find-GDriveFolder -Name $segment -ParentId $parent -AccessToken $AccessToken
        if (-not $id) {
            $id = New-GDriveFolder -Name $segment -ParentId $parent -AccessToken $AccessToken
        }
        $parent = $id
    }
    return $parent
}

# === File metadata / delete / quota =======================================

function Get-GDriveFileById {
    # files.get metadata (NOT content - use Receive-GDriveFile for bytes).
    param(
        [Parameter(Mandatory)] [string]$FileId,
        [string]$Fields = 'id,name,size,sha256Checksum,createdTime,appProperties,parents',
        [string]$AccessToken
    )
    if (Test-GDriveMock) {
        if (-not (Test-Path -LiteralPath $FileId)) {
            throw "Drive API GET files/$FileId failed (HTTP 404, client_error): mock file not found"
        }
        $metaPath = "$FileId.gdrivemeta.json"
        if (Test-Path -LiteralPath $metaPath) {
            return (Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json)
        }
        $item = Get-Item -LiteralPath $FileId
        return [pscustomobject]@{
            id             = $FileId
            name           = $item.Name
            size           = "$($item.Length)"
            sha256Checksum = (Get-FileHash -LiteralPath $FileId -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return Invoke-GDriveApi -Method Get -Uri "files/$FileId" -AccessToken $AccessToken `
        -Query @{ fields = $Fields }
}

function Remove-GDriveFile {
    # files.delete; a 404 is tolerated (idempotent cleanup paths re-delete).
    param(
        [Parameter(Mandatory)] [string]$FileId,
        [string]$AccessToken
    )
    if (Test-GDriveMock) {
        if (Test-Path -LiteralPath $FileId) {
            Remove-Item -LiteralPath $FileId -Force -Recurse -Confirm:$false -ErrorAction Stop
        }
        $metaPath = "$FileId.gdrivemeta.json"
        if (Test-Path -LiteralPath $metaPath) {
            Remove-Item -LiteralPath $metaPath -Force -Confirm:$false -ErrorAction SilentlyContinue
        }
        return
    }
    try {
        Invoke-GDriveApi -Method Delete -Uri "files/$FileId" -AccessToken $AccessToken | Out-Null
    } catch {
        if ($_.Exception.Message -match 'HTTP 404') { return }
        throw
    }
}

function Get-GDriveAbout {
    # about.get?fields=storageQuota,user - works under the drive.file scope.
    # Caller caches the result to ir.config_parameter wms_gdrive.last_about.
    param([string]$AccessToken)
    if (Test-GDriveMock) {
        $root = Get-GDriveMockRoot
        $used = [long]0
        Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike '*.gdrivemeta.json' } |
            ForEach-Object { $used += $_.Length }
        return [pscustomobject]@{
            storageQuota = [pscustomobject]@{
                limit        = '16106127360'   # synthetic 15 GB free-Gmail quota
                usage        = "$used"
                usageInDrive = "$used"
            }
            user = [pscustomobject]@{
                emailAddress = 'mock@gdrive.local'
                displayName  = 'GDrive Mock'
            }
        }
    }
    return Invoke-GDriveApi -Method Get -Uri 'about' -AccessToken $AccessToken `
        -Query @{ fields = 'storageQuota,user' }
}

# === Upload ===============================================================

function Send-GDriveFileMultipart {
    # uploadType=multipart for files <= 5 MB (one POST, metadata + media in a
    # related-multipart body). Plain Invoke-RestMethod - no HttpClient needed.
    param(
        [Parameter(Mandatory)] [string]$LocalPath,
        [Parameter(Mandatory)] [hashtable]$Metadata,
        [string]$AccessToken
    )
    $boundary = 'wms_gdrive_' + [guid]::NewGuid().ToString('N')
    $metaJson = $Metadata | ConvertTo-Json -Depth 6 -Compress
    $nl   = "`r`n"
    $head = "--$boundary$nl" +
            "Content-Type: application/json; charset=UTF-8$nl$nl" +
            $metaJson + $nl +
            "--$boundary$nl" +
            "Content-Type: application/octet-stream$nl$nl"
    $tail = "$nl--$boundary--$nl"
    $headBytes = [System.Text.Encoding]::UTF8.GetBytes($head)
    $fileBytes = [System.IO.File]::ReadAllBytes($LocalPath)
    $tailBytes = [System.Text.Encoding]::UTF8.GetBytes($tail)
    $bodyBytes = New-Object byte[] ($headBytes.Length + $fileBytes.Length + $tailBytes.Length)
    [Buffer]::BlockCopy($headBytes, 0, $bodyBytes, 0, $headBytes.Length)
    [Buffer]::BlockCopy($fileBytes, 0, $bodyBytes, $headBytes.Length, $fileBytes.Length)
    [Buffer]::BlockCopy($tailBytes, 0, $bodyBytes, $headBytes.Length + $fileBytes.Length, $tailBytes.Length)
    $uri = "$script:GDriveUploadBase/files?uploadType=multipart&fields=" +
           [uri]::EscapeDataString('id,name,size,sha256Checksum')
    return Invoke-RestMethod -Method Post -Uri $uri -TimeoutSec 300 `
        -Headers @{ Authorization = "Bearer $AccessToken" } `
        -ContentType "multipart/related; boundary=$boundary" -Body $bodyBytes
}

function Send-GDriveFileResumable {
    # uploadType=resumable for files > 5 MB. Chunked PUTs of 8 MiB via
    # System.Net.Http.HttpClient (Invoke-WebRequest cannot set Content-Range
    # per chunk). 308 + Range header drives the offset; on a transient error
    # the session is queried (PUT, Content-Range: bytes */total) and resumed.
    # A dead session (404) is restarted once. Chunk-level resumes do NOT
    # consume the caller's per-file attempt budget.
    param(
        [Parameter(Mandatory)] [string]$LocalPath,
        [Parameter(Mandatory)] [hashtable]$Metadata,
        [Parameter(Mandatory)] [long]$Size,
        [string]$AccessToken
    )
    Add-Type -AssemblyName System.Net.Http

    $initUri = "$script:GDriveUploadBase/files?uploadType=resumable&fields=" +
               [uri]::EscapeDataString('id,name,size,sha256Checksum')
    $initHeaders = @{
        Authorization             = "Bearer $AccessToken"
        'X-Upload-Content-Type'   = 'application/octet-stream'
        'X-Upload-Content-Length' = "$Size"
    }
    $initBody = $Metadata | ConvertTo-Json -Depth 6 -Compress

    $newSession = {
        $initResp = Invoke-WebRequest -Method Post -Uri $initUri -Headers $initHeaders `
            -ContentType 'application/json; charset=utf-8' -Body $initBody `
            -TimeoutSec 60 -UseBasicParsing
        $loc = [string]$initResp.Headers['Location']
        if (-not $loc) { throw 'resumable upload initiation returned no Location header' }
        $loc
    }

    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(30)
    $client.DefaultRequestHeaders.Authorization =
        New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $AccessToken)
    $fs = [System.IO.File]::OpenRead($LocalPath)
    try {
        $sessionUri = & $newSession
        $offset = [long]0
        $stalls = 0              # consecutive no-progress events; hard stop at 5
        $sessionRestarted = $false
        while ($true) {
            $len = [long][Math]::Min([long]$script:GDriveChunkSize, $Size - $offset)
            $buf = New-Object byte[] $len
            $fs.Position = $offset
            $read = 0
            while ($read -lt $len) {
                $n = $fs.Read($buf, $read, [int]($len - $read))
                if ($n -le 0) { throw "unexpected EOF reading $LocalPath at offset $($offset + $read)" }
                $read += $n
            }
            $status = 0; $respText = ''; $rangeHeader = ''
            try {
                $content = New-Object System.Net.Http.ByteArrayContent -ArgumentList @(, $buf)
                $content.Headers.ContentType =
                    New-Object System.Net.Http.Headers.MediaTypeHeaderValue('application/octet-stream')
                $content.Headers.ContentRange =
                    New-Object System.Net.Http.Headers.ContentRangeHeaderValue($offset, ($offset + $len - 1), $Size)
                $put = $client.PutAsync($sessionUri, $content).GetAwaiter().GetResult()
                try {
                    $status = [int]$put.StatusCode
                    if ($null -ne $put.Content) {
                        $respText = $put.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                    }
                    $vals = $null
                    if ($put.Headers.TryGetValues('Range', [ref]$vals)) { $rangeHeader = [string](@($vals)[0]) }
                } finally { $put.Dispose() }
            } catch {
                $status = 0   # network drop mid-chunk -> query-and-resume below
            }

            if ($status -eq 200 -or $status -eq 201) {
                return ($respText | ConvertFrom-Json)
            }
            if ($status -eq 308) {
                # Range: bytes=0-N means N+1 bytes are stored; absent = none.
                $newOffset = [long]0
                if ($rangeHeader -match 'bytes=0-(\d+)') { $newOffset = [long]$Matches[1] + 1 }
                if ($newOffset -gt $offset) { $stalls = 0 } else { $stalls++ }
                $offset = $newOffset
                if ($stalls -gt 5) { throw 'resumable upload made no progress over 5 consecutive chunks' }
                continue
            }
            if (($status -in 429, 500, 502, 503, 504) -or $status -eq 0) {
                $stalls++
                if ($stalls -gt 5) {
                    throw "resumable upload failed after repeated interruptions (last HTTP $status)"
                }
                Start-Sleep -Milliseconds (([math]::Pow(2, [Math]::Min($stalls, 3)) * 1000) + (Get-Random -Maximum 1000))
                # Query session state: empty PUT with Content-Range: bytes */<total>.
                $qStatus = 0; $qText = ''; $qRange = ''
                try {
                    $qContent = New-Object System.Net.Http.ByteArrayContent -ArgumentList @(, (New-Object byte[] 0))
                    $qContent.Headers.ContentRange =
                        New-Object System.Net.Http.Headers.ContentRangeHeaderValue($Size)
                    $qResp = $client.PutAsync($sessionUri, $qContent).GetAwaiter().GetResult()
                    try {
                        $qStatus = [int]$qResp.StatusCode
                        if ($null -ne $qResp.Content) {
                            $qText = $qResp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                        }
                        $vals = $null
                        if ($qResp.Headers.TryGetValues('Range', [ref]$vals)) { $qRange = [string](@($vals)[0]) }
                    } finally { $qResp.Dispose() }
                } catch {
                    continue   # still offline; next loop pass backs off again
                }
                if ($qStatus -eq 200 -or $qStatus -eq 201) { return ($qText | ConvertFrom-Json) }
                if ($qStatus -eq 308) {
                    $newOffset = [long]0
                    if ($qRange -match 'bytes=0-(\d+)') { $newOffset = [long]$Matches[1] + 1 }
                    if ($newOffset -gt $offset) { $stalls = 0 }
                    $offset = $newOffset
                    continue
                }
                if ($qStatus -eq 404 -and -not $sessionRestarted) {
                    # Session expired server-side; one fresh session, from byte 0.
                    $sessionRestarted = $true
                    $sessionUri = & $newSession
                    $offset = [long]0
                    $stalls = 0
                    continue
                }
                throw "resumable upload session query failed (HTTP $qStatus): $qText"
            }
            # Hard 4xx on a chunk - no point resuming.
            throw "resumable chunk upload failed (HTTP $status): $respText"
        }
    } finally {
        $fs.Dispose()
        $client.Dispose()
    }
}

function Send-GDriveFile {
    # Upload one local file into a Drive folder and PROVE it arrived intact:
    #   1. collision pre-flight (same name in folder: identical sha -> reuse,
    #      different -> delete the stale remote then upload)
    #   2. multipart <= 5 MB, resumable above
    #   3. verify response sha256Checksum + size against the local file
    #      (files.get re-poll covers checksum-population lag); on mismatch the
    #      remote copy is deleted and the attempt counts as failed
    # 3 full attempts with 2 s/4 s/8 s + jitter between them. Local artifacts
    # are NEVER touched. Returns the Drive file object
    # (id, name, size, sha256Checksum).
    param(
        [Parameter(Mandatory)] [string]$LocalPath,
        [Parameter(Mandatory)] [string]$RemoteName,
        [Parameter(Mandatory)] [string]$ParentId,
        [hashtable]$AppProperties,
        [string]$ExpectedSha256,
        [string]$AccessToken
    )
    if (-not (Test-Path -LiteralPath $LocalPath)) {
        throw "Send-GDriveFile: local file not found: $LocalPath"
    }
    $size = [long](Get-Item -LiteralPath $LocalPath).Length
    if (-not $ExpectedSha256) {
        $ExpectedSha256 = (Get-FileHash -LiteralPath $LocalPath -Algorithm SHA256).Hash
    }

    if (Test-GDriveMock) {
        $parentPath = Resolve-GDriveMockId $ParentId
        if (-not (Test-Path -LiteralPath $parentPath -PathType Container)) {
            throw "Send-GDriveFile (mock): parent folder not found: $ParentId"
        }
        $dest = Join-Path $parentPath $RemoteName
        Copy-Item -LiteralPath $LocalPath -Destination $dest -Force
        $gotHash = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
        if ($gotHash -ne $ExpectedSha256) {   # -eq/-ne are case-insensitive on strings
            Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
            throw "Send-GDriveFile (mock): sha256 mismatch for $RemoteName after copy; remote copy deleted"
        }
        Write-GDriveMockMeta -FilePath $dest -AppProperties $AppProperties -Sha256 $gotHash
        return [pscustomobject]@{
            id             = $dest
            name           = $RemoteName
            size           = "$size"
            sha256Checksum = $gotHash.ToLowerInvariant()
        }
    }

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            # 1. Collision pre-flight (a previous run may have died after the
            #    upload but before bookkeeping).
            $escName   = ConvertTo-GDriveQueryLiteral $RemoteName
            $escParent = ConvertTo-GDriveQueryLiteral $ParentId
            $existing = Invoke-GDriveApi -Method Get -Uri 'files' -AccessToken $AccessToken -Query @{
                q        = "name='$escName' and '$escParent' in parents and trashed=false"
                fields   = 'files(id,name,size,sha256Checksum)'
                pageSize = '10'
                spaces   = 'drive'
            }
            foreach ($f in @(Get-GDriveProp $existing 'files' @())) {
                $fSha = [string](Get-GDriveProp $f 'sha256Checksum' '')
                if ($fSha -and ($fSha -eq $ExpectedSha256)) { return $f }
                Remove-GDriveFile -FileId ([string]$f.id) -AccessToken $AccessToken
            }

            # 2. Upload.
            $meta = @{ name = $RemoteName; parents = @($ParentId) }
            if ($AppProperties -and $AppProperties.Count -gt 0) { $meta['appProperties'] = $AppProperties }
            if ($size -le $script:GDriveSimpleUploadMax) {
                $file = Send-GDriveFileMultipart -LocalPath $LocalPath -Metadata $meta -AccessToken $AccessToken
            } else {
                $file = Send-GDriveFileResumable -LocalPath $LocalPath -Metadata $meta -Size $size -AccessToken $AccessToken
            }

            # 3. Verify WITHOUT re-download. sha256Checksum can lag a few
            #    seconds on freshly-uploaded large files -> bounded re-poll.
            $fileId     = [string](Get-GDriveProp $file 'id' '')
            $remoteSha  = [string](Get-GDriveProp $file 'sha256Checksum' '')
            $remoteSize = [long](Get-GDriveProp $file 'size' 0)
            for ($poll = 0; (-not $remoteSha) -and $poll -lt 5; $poll++) {
                Start-Sleep -Seconds 3
                $file = Get-GDriveFileById -FileId $fileId -Fields 'id,name,size,sha256Checksum' -AccessToken $AccessToken
                $remoteSha  = [string](Get-GDriveProp $file 'sha256Checksum' '')
                $remoteSize = [long](Get-GDriveProp $file 'size' 0)
            }
            if (($remoteSha -ne $ExpectedSha256) -or ($remoteSize -ne $size)) {
                if ($fileId) { Remove-GDriveFile -FileId $fileId -AccessToken $AccessToken }
                throw "upload verification failed for $RemoteName (remote sha256=$remoteSha size=$remoteSize vs local sha256=$ExpectedSha256 size=$size); corrupt remote copy deleted"
            }
            return $file
        } catch {
            # An expired grant cannot heal by retrying - surface immediately.
            if ($_.Exception.Message -match 'GDRIVE_AUTH_EXPIRED') { throw }
            if ($attempt -lt $maxAttempts) {
                Start-Sleep -Milliseconds (([math]::Pow(2, $attempt) * 1000) + (Get-Random -Maximum 1000))
                continue
            }
            throw
        }
    }
}

# === Download / listing ===================================================

function Receive-GDriveFile {
    # GET files/<id>?alt=media streamed to disk (HttpClient, 64 KB buffer -
    # backup artifacts can exceed what Invoke-WebRequest buffers comfortably).
    # SHA-256 verified when ExpectedSha256 is given; a partial or corrupt
    # download is deleted before throwing. Returns the FileInfo of OutPath.
    param(
        [Parameter(Mandatory)] [string]$FileId,
        [Parameter(Mandatory)] [string]$OutPath,
        [string]$ExpectedSha256,
        [string]$AccessToken
    )
    $dir = Split-Path -Parent $OutPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    if (Test-GDriveMock) {
        if (-not (Test-Path -LiteralPath $FileId)) {
            throw "Receive-GDriveFile (mock): file not found: $FileId"
        }
        Copy-Item -LiteralPath $FileId -Destination $OutPath -Force
    } else {
        Add-Type -AssemblyName System.Net.Http
        $client = New-Object System.Net.Http.HttpClient
        $client.Timeout = [TimeSpan]::FromHours(2)
        $client.DefaultRequestHeaders.Authorization =
            New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $AccessToken)
        $resp = $null; $inStream = $null; $outStream = $null
        try {
            $resp = $client.GetAsync("$script:GDriveApiBase/files/$FileId`?alt=media",
                [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            if (-not $resp.IsSuccessStatusCode) {
                $errText = ''
                try { $errText = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult() } catch { }
                throw "Drive download of $FileId failed (HTTP $([int]$resp.StatusCode)): $errText"
            }
            $inStream  = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $outStream = [System.IO.File]::Create($OutPath)
            $buf = New-Object byte[] 65536
            while (($n = $inStream.Read($buf, 0, $buf.Length)) -gt 0) {
                $outStream.Write($buf, 0, $n)
            }
            $outStream.Dispose()
            $outStream = $null
        } catch {
            if ($null -ne $outStream) { $outStream.Dispose(); $outStream = $null }
            # Never leave a partial download behind.
            if (Test-Path -LiteralPath $OutPath) {
                Remove-Item -LiteralPath $OutPath -Force -ErrorAction SilentlyContinue
            }
            throw
        } finally {
            if ($null -ne $outStream) { $outStream.Dispose() }
            if ($null -ne $inStream)  { $inStream.Dispose() }
            if ($null -ne $resp)      { $resp.Dispose() }
            $client.Dispose()
        }
    }
    if ($ExpectedSha256) {
        $gotHash = (Get-FileHash -LiteralPath $OutPath -Algorithm SHA256).Hash
        if ($gotHash -ne $ExpectedSha256) {
            Remove-Item -LiteralPath $OutPath -Force -ErrorAction SilentlyContinue
            throw "downloaded file failed SHA-256 verification (expected $ExpectedSha256, got $gotHash); partial file deleted"
        }
    }
    return (Get-Item -LiteralPath $OutPath)
}

function Get-GDriveBackupSets {
    # Flat appProperties query over every file this app uploaded
    # (wms_backup='1'), paged via nextPageToken. Returns a flat file array
    # (id,name,size,createdTime,appProperties,parents); callers group by
    # appProperties.set_id. ExtraQ is appended verbatim to the q string
    # (pass it with a leading ' and ').
    param(
        [string]$AccessToken,
        [string]$ExtraQ = ''
    )
    if (Test-GDriveMock) {
        # Mock supports the one ExtraQ shape the scripts use:
        #   appProperties has { key='k' and value='v' }   (and-chained)
        $filters = @()
        if ($ExtraQ) {
            $rx = [regex] "appProperties\s+has\s+\{\s*key='([^']+)'\s+and\s+value='([^']*)'\s*\}"
            foreach ($fm in $rx.Matches($ExtraQ)) {
                $filters += , @($fm.Groups[1].Value, $fm.Groups[2].Value)
            }
        }
        $root = Get-GDriveMockRoot
        $result = New-Object System.Collections.Generic.List[object]
        $metas = @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.gdrivemeta.json' -ErrorAction SilentlyContinue)
        foreach ($m in $metas) {
            $obj = $null
            try { $obj = Get-Content -LiteralPath $m.FullName -Raw | ConvertFrom-Json } catch { continue }
            $props = Get-GDriveProp $obj 'appProperties' $null
            if ([string](Get-GDriveProp $props 'wms_backup' '') -ne '1') { continue }
            $match = $true
            foreach ($flt in $filters) {
                if ([string](Get-GDriveProp $props $flt[0] '') -ne $flt[1]) { $match = $false; break }
            }
            if ($match) { $result.Add($obj) }
        }
        # .ToArray(), not @($list): PS 5.1 under Set-StrictMode -Version Latest
        # throws 'Argument types do not match' when @() wraps a generic List.
        # No comma wrapper - callers re-collect with @( ) themselves.
        return $result.ToArray()
    }
    $q = "appProperties has { key='wms_backup' and value='1' } and trashed=false"
    if ($ExtraQ) { $q = $q + $ExtraQ }
    $all = New-Object System.Collections.Generic.List[object]
    $pageToken = ''
    do {
        $query = @{
            q        = $q
            fields   = 'nextPageToken,files(id,name,size,createdTime,appProperties,parents)'
            pageSize = '1000'
            spaces   = 'drive'
        }
        if ($pageToken) { $query['pageToken'] = $pageToken }
        $res = Invoke-GDriveApi -Method Get -Uri 'files' -AccessToken $AccessToken -Query $query
        foreach ($f in @(Get-GDriveProp $res 'files' @())) { $all.Add($f) }
        $pageToken = [string](Get-GDriveProp $res 'nextPageToken' '')
    } while ($pageToken)
    # .ToArray() instead of @() - see the mock branch note (PS 5.1 StrictMode bug).
    return $all.ToArray()
}

# === Retention ============================================================

function Get-GDriveIsoWeekKey {
    # ISO-8601 week bucket key. .NET Framework (PS 5.1) has no
    # System.Globalization.ISOWeek: shift Mon-Wed dates +3 days so
    # GetWeekOfYear's FirstFourDayWeek rule lands in the ISO year, then key
    # on the shifted year + week. Early-January W52/W53 edge cases may fork
    # an extra bucket, which at worst KEEPS one extra weekly set - never
    # deletes more.
    param([Parameter(Mandatory)] [datetime]$Date)
    $d = $Date
    $dow = [int]$d.DayOfWeek            # Sunday = 0
    if ($dow -ge 1 -and $dow -le 3) { $d = $d.AddDays(3) }
    $cal = [System.Globalization.CultureInfo]::InvariantCulture.Calendar
    $week = $cal.GetWeekOfYear($d,
        [System.Globalization.CalendarWeekRule]::FirstFourDayWeek, [DayOfWeek]::Monday)
    return ('{0}-W{1:00}' -f $d.Year, $week)
}

function Invoke-GDriveRetention {
    # Drive-side tiered retention, run only after a successful upload:
    #   tier 1: every set within daily_days (default 30 d)
    #   tier 2: newest set per ISO week within weekly_months (default 6 mo)
    #   tier 3: newest set per calendar month within monthly_years (default 2 y)
    #   older:  delete
    # Manual + emergency sets are exempt unless DeleteManual. Sets with an
    # unparsable date are kept (never delete on doubt). Day folders emptied by
    # deletions are removed; month/year folders stay (cosmetic).
    # NEVER throws - retention is housekeeping, not a backup-failure cause.
    # Returns a one-line summary for the backup_gdrive audit message.
    param(
        [string]$AccessToken,
        [hashtable]$Tiers,
        [bool]$DeleteManual = $false
    )
    try {
        $dailyDays = 30; $weeklyMonths = 6; $monthlyYears = 2
        if ($Tiers) {
            $v = 0
            if ($Tiers.ContainsKey('daily_days')     -and [int]::TryParse("$($Tiers['daily_days'])", [ref]$v)     -and $v -gt 0) { $dailyDays = $v }
            if ($Tiers.ContainsKey('weekly_months')  -and [int]::TryParse("$($Tiers['weekly_months'])", [ref]$v)  -and $v -gt 0) { $weeklyMonths = $v }
            if ($Tiers.ContainsKey('monthly_years')  -and [int]::TryParse("$($Tiers['monthly_years'])", [ref]$v)  -and $v -gt 0) { $monthlyYears = $v }
        }
        $files = @(Get-GDriveBackupSets -AccessToken $AccessToken)
        if ($files.Count -eq 0) { return 'retention: no backup sets on Drive' }

        # Group files into sets by appProperties.set_id.
        $sets = @{ }
        foreach ($f in $files) {
            $props = Get-GDriveProp $f 'appProperties' $null
            $setId = [string](Get-GDriveProp $props 'set_id' '')
            if (-not $setId) { continue }   # untagged files are never touched
            if (-not $sets.ContainsKey($setId)) {
                $dateStr = [string](Get-GDriveProp $props 'backup_date' '')
                $setDate = $null
                $parsed = [datetime]::MinValue
                if ($dateStr -and [datetime]::TryParseExact($dateStr, 'yyyy-MM-dd',
                        [System.Globalization.CultureInfo]::InvariantCulture,
                        [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
                    $setDate = $parsed.Date
                } elseif ($setId -match '^(\d{4})(\d{2})(\d{2})-' ) {
                    try { $setDate = (Get-Date -Year $Matches[1] -Month $Matches[2] -Day $Matches[3]).Date } catch { $setDate = $null }
                }
                $sets[$setId] = [pscustomobject]@{
                    SetId = $setId
                    Date  = $setDate
                    Type  = [string](Get-GDriveProp $props 'backup_type' 'auto')
                    Files = (New-Object System.Collections.Generic.List[object])
                }
            }
            $sets[$setId].Files.Add($f)
        }

        $today         = (Get-Date).Date
        $dailyCutoff   = $today.AddDays(-$dailyDays)
        $weeklyCutoff  = $today.AddMonths(-$weeklyMonths)
        $monthlyCutoff = $today.AddYears(-$monthlyYears)
        $weekSeen  = @{ }
        $monthSeen = @{ }
        $keptDaily = 0; $keptWeekly = 0; $keptMonthly = 0; $exempt = 0; $deletedSets = 0
        $deleteFiles = New-Object System.Collections.Generic.List[object]
        $affectedParents = @{ }

        # Newest-first so "newest per bucket" = first seen per bucket
        # (set_stamp is lexicographically chronological).
        foreach ($set in ($sets.Values | Sort-Object -Property SetId -Descending)) {
            if ($null -eq $set.Date) { $exempt++; continue }
            if (($set.Type -eq 'manual' -or $set.Type -eq 'emergency') -and -not $DeleteManual) {
                $exempt++
                continue
            }
            $keep = $false
            if ($set.Date -ge $dailyCutoff) {
                $keep = $true; $keptDaily++
            } elseif ($set.Date -ge $weeklyCutoff) {
                $wk = Get-GDriveIsoWeekKey -Date $set.Date
                if (-not $weekSeen.ContainsKey($wk)) { $weekSeen[$wk] = $set.SetId; $keep = $true; $keptWeekly++ }
            } elseif ($set.Date -ge $monthlyCutoff) {
                $mk = $set.Date.ToString('yyyy-MM')
                if (-not $monthSeen.ContainsKey($mk)) { $monthSeen[$mk] = $set.SetId; $keep = $true; $keptMonthly++ }
            }
            if ($keep) { continue }
            $deletedSets++
            foreach ($f in $set.Files) { $deleteFiles.Add($f) }
        }

        foreach ($f in $deleteFiles) {
            $fid = [string](Get-GDriveProp $f 'id' '')
            if (-not $fid) { continue }
            foreach ($p in @(Get-GDriveProp $f 'parents' @())) { $affectedParents["$p"] = $true }
            try {
                Remove-GDriveFile -FileId $fid -AccessToken $AccessToken
            } catch {
                Write-Host "    [warn] Drive retention: could not delete $fid (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
            }
        }

        # Remove day folders the deletions emptied (parents of deleted files).
        # NOTE: $pid is OFF-LIMITS as a loop variable (read-only automatic var).
        foreach ($folderId in @($affectedParents.Keys)) {
            try {
                if (Test-GDriveMock) {
                    if ((Test-Path -LiteralPath $folderId -PathType Container) -and
                        (@(Get-ChildItem -LiteralPath $folderId -Force -ErrorAction SilentlyContinue).Count -eq 0)) {
                        Remove-Item -LiteralPath $folderId -Force -Confirm:$false
                    }
                } else {
                    $escFolderId = ConvertTo-GDriveQueryLiteral $folderId
                    $chk = Invoke-GDriveApi -Method Get -Uri 'files' -AccessToken $AccessToken -Query @{
                        q        = "'$escFolderId' in parents and trashed=false"
                        fields   = 'files(id)'
                        pageSize = '1'
                        spaces   = 'drive'
                    }
                    if (@(Get-GDriveProp $chk 'files' @()).Count -eq 0) {
                        Remove-GDriveFile -FileId $folderId -AccessToken $AccessToken
                    }
                }
            } catch {
                Write-Host "    [warn] Drive retention: day-folder cleanup skipped (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
            }
        }

        $summary = "kept $keptDaily daily / $keptWeekly weekly / $keptMonthly monthly, deleted $deletedSets set(s)"
        if ($exempt -gt 0) { $summary = "$summary; $exempt manual/emergency-exempt" }
        return $summary
    } catch {
        Write-Host "    [warn] Drive retention skipped (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
        return "retention skipped: $($_.Exception.Message)"
    }
}

# === Set metadata (appProperties / backup-info.json) ======================

function New-GDriveAppProperties {
    # Per-file appProperties (each key+value must stay <= 124 bytes):
    # wms_backup='1' tags app uploads for the flat retention/restore query;
    # set_id groups the 4-file set; backup_type drives retention exemption.
    param(
        [Parameter(Mandatory)] [string]$SetStamp,
        [Parameter(Mandatory)] [ValidateSet('db', 'filestore', 'sha256', 'info')] [string]$Role,
        [ValidateSet('auto', 'manual', 'emergency')] [string]$BackupType = 'auto',
        [string]$DbName = 'wms',
        [string]$BackupDate = ''
    )
    if (-not $BackupDate) {
        if ($SetStamp -match '^(\d{4})(\d{2})(\d{2})-') {
            $BackupDate = '{0}-{1}-{2}' -f $Matches[1], $Matches[2], $Matches[3]
        } else {
            $BackupDate = (Get-Date).ToString('yyyy-MM-dd')
        }
    }
    return @{
        wms_backup  = '1'
        set_id      = $SetStamp
        role        = $Role
        backup_type = $BackupType
        db          = $DbName
        backup_date = $BackupDate
    }
}

function New-BackupInfoJson {
    # backup-info.json for one backup set (schema_version 1). Carries the
    # local_name <-> drive_name mapping gdrive-restore.ps1 uses to rename
    # downloads back to the local convention. Files entries: hashtables with
    # role / local_name / drive_name / size_bytes / sha256 (filestore entry
    # omitted by the caller when that stage was skipped). Returns the JSON
    # string; also writes it to OutPath (UTF-8, no BOM) when given.
    param(
        [Parameter(Mandatory)] [string]$SetStamp,
        [Parameter(Mandatory)] [string]$DbName,
        [ValidateSet('auto', 'manual', 'emergency')] [string]$BackupType = 'auto',
        [string]$Creator = 'system (scheduled)',
        [string]$WmsVersion = 'unknown',
        [int]$TocEntries = 0,
        [object[]]$Files = @(),
        [string]$OutPath = ''
    )
    $now = Get-Date
    $fileEntries = @()
    foreach ($f in $Files) {
        $fileEntries += [ordered]@{
            role       = [string](Get-GDriveProp $f 'role' '')
            local_name = [string](Get-GDriveProp $f 'local_name' '')
            drive_name = [string](Get-GDriveProp $f 'drive_name' '')
            size_bytes = [long](Get-GDriveProp $f 'size_bytes' 0)
            sha256     = ([string](Get-GDriveProp $f 'sha256' '')).ToLowerInvariant()
        }
    }
    $doc = [ordered]@{
        schema_version  = 1
        set_stamp       = $SetStamp
        timestamp_utc   = $now.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        timestamp_local = $now.ToString('yyyy-MM-dd HH:mm:ss zzz')
        db_name         = $DbName
        backup_type     = $BackupType
        creator         = $Creator
        hostname        = "$env:COMPUTERNAME"
        wms_version     = $WmsVersion
        odoo_version    = '19.0'
        encryption      = [ordered]@{
            encrypted = $true
            algorithm = 'GPG symmetric AES256'
            note      = 'passphrase is NEVER stored on Drive'
        }
        toc_entries     = $TocEntries
        files           = $fileEntries
        retention       = [ordered]@{ manual_exempt = ($BackupType -ne 'auto') }
        restore_hint    = "scripts\gdrive-restore.ps1 -SetStamp $SetStamp"
    }
    $json = $doc | ConvertTo-Json -Depth 6
    if ($OutPath) {
        [System.IO.File]::WriteAllText($OutPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    }
    return $json
}

# === psql catalog / config bridge =========================================

function Write-GDriveCatalogRow {
    # UPSERT one row into wms_gdrive_backup via psql (SELECT id by name ->
    # UPDATE, else INSERT). FAILURE-SAFE (Write-BackupAudit pattern): any
    # psql/DB problem degrades to a DarkGray note - the backup never fails
    # over bookkeeping. Single quotes doubled; create_uid/write_uid = 1;
    # NOW() stamps create/write_date.
    # COLUMN CONTRACT: keys below mirror addons/wms_reports/models/
    # wms_gdrive_backup.py - any field rename/addition must update both in
    # the same commit (psql bypasses the ORM).
    param(
        [Parameter(Mandatory)] [hashtable]$Row,
        [string]$DbName,
        [string]$DbHost,
        [int]$DbPort,
        [string]$DbUser
    )
    try {
        if (-not $Row.ContainsKey('name') -or -not $Row['name']) {
            throw "catalog row requires a 'name' key (local db filename)"
        }
        $conn = Resolve-WmsDbConnection -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
        $allowed = @(
            'name', 'set_stamp', 'db_name', 'backup_type', 'backup_time',
            'year', 'month_label', 'day', 'drive_name', 'drive_file_id',
            'drive_folder', 'filestore_drive_id', 'size_mb', 'checksum',
            'uploaded', 'upload_time', 'creator', 'encrypted', 'wms_version',
            'info_json', 'restored_count'
        )
        $colSql = [ordered]@{ }
        foreach ($col in $allowed) {
            if (-not $Row.ContainsKey($col)) { continue }
            $v = $Row[$col]
            if ($null -eq $v) {
                $colSql[$col] = 'NULL'
            } elseif ($v -is [bool]) {
                if ($v) { $colSql[$col] = 'true' } else { $colSql[$col] = 'false' }
            } elseif ($v -is [datetime]) {
                # Odoo stores naive UTC timestamps.
                $colSql[$col] = "'" + $v.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') + "'"
            } elseif ($v -is [int] -or $v -is [long] -or $v -is [double] -or $v -is [single] -or $v -is [decimal]) {
                $colSql[$col] = [System.Convert]::ToString($v, [System.Globalization.CultureInfo]::InvariantCulture)
            } else {
                $colSql[$col] = "'" + ("$v" -replace "'", "''") + "'"
            }
        }
        # A row marked uploaded gets an upload_time even if the caller forgot.
        if ($Row.ContainsKey('uploaded') -and $Row['uploaded'] -eq $true -and -not $Row.ContainsKey('upload_time')) {
            $colSql['upload_time'] = 'NOW()'
        }

        $escName = ($Row['name'] -replace "'", "''")
        $sel = & psql -U $conn.DbUser -h $conn.DbHost -p $conn.DbPort -d $conn.DbName -w -t -A `
            -v ON_ERROR_STOP=1 -c "SELECT id FROM wms_gdrive_backup WHERE name = '$escName' ORDER BY id DESC LIMIT 1;" 2>$null
        $rowId = ''
        if ($LASTEXITCODE -eq 0 -and $sel) {
            $rowId = [string](@($sel) | Where-Object { "$_" -match '^\s*\d+\s*$' } | Select-Object -First 1)
            $rowId = $rowId.Trim()
        }

        if ($rowId -match '^\d+$') {
            $assignments = @()
            foreach ($col in $colSql.Keys) { $assignments += "$col = $($colSql[$col])" }
            $assignments += 'write_uid = 1'
            $assignments += 'write_date = NOW()'
            $sql = "UPDATE wms_gdrive_backup SET $($assignments -join ', ') WHERE id = $rowId;"
        } else {
            $cols = @($colSql.Keys) + @('create_uid', 'create_date', 'write_uid', 'write_date')
            $vals = @($colSql.Values) + @('1', 'NOW()', '1', 'NOW()')
            $sql = "INSERT INTO wms_gdrive_backup ($($cols -join ', ')) VALUES ($($vals -join ', '));"
        }
        $sql | & psql -U $conn.DbUser -h $conn.DbHost -p $conn.DbPort -d $conn.DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [audit] recorded catalog row in wms_gdrive_backup" -ForegroundColor DarkGray
        } else {
            Write-Host "    [warn] gdrive catalog row not recorded (is wms_reports >= 19.0.3.0.0 installed?)" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] gdrive catalog write failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Get-WmsConfigParam {
    # Remote config channel: ir.config_parameter read via psql. Failure-safe -
    # returns Default on ANY error so a down DB never blocks a local backup.
    param(
        [Parameter(Mandatory)] [string]$Key,
        [string]$Default = '',
        [string]$DbName,
        [string]$DbHost,
        [int]$DbPort,
        [string]$DbUser
    )
    try {
        $conn = Resolve-WmsDbConnection -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
        $escKey = ($Key -replace "'", "''")
        $out = & psql -U $conn.DbUser -h $conn.DbHost -p $conn.DbPort -d $conn.DbName -w -t -A `
            -v ON_ERROR_STOP=1 -c "SELECT value FROM ir_config_parameter WHERE key = '$escKey' LIMIT 1;" 2>$null
        if ($LASTEXITCODE -ne 0) { return $Default }
        $val = @($out) | Where-Object { $null -ne $_ -and "$_".Trim() -ne '' } | Select-Object -First 1
        if ($null -eq $val) { return $Default }
        return "$val".Trim()
    } catch {
        return $Default
    }
}

# === Stage gate ============================================================

function Test-GDriveReady {
    # The Drive-stage gate for backup-native.ps1: $true only when the token
    # file exists (hard gate - written by setup-gdrive-auth.ps1) AND client
    # id/secret are non-blank in .env (skipped in mock mode, which needs no
    # credentials) AND the wms_gdrive.enabled soft kill-switch is not '0'
    # (default '1'; unreadable DB counts as enabled - failure-safe).
    param(
        [Parameter(Mandatory)] [string]$EnvPath,
        [Parameter(Mandatory)] [string]$TokenPath,
        [string]$DbName,
        [string]$DbHost,
        [int]$DbPort,
        [string]$DbUser
    )
    if (-not (Test-Path -LiteralPath $TokenPath)) { return $false }
    if (-not (Test-GDriveMock)) {
        $cfg = $null
        try {
            $cfg = Get-GDriveEnvConfig -EnvPath $EnvPath
        } catch {
            Write-Host "    [warn] Drive config rejected: $($_.Exception.Message)" -ForegroundColor DarkGray
            return $false
        }
        if (-not $cfg.ClientId -or -not $cfg.ClientSecret) { return $false }
    }
    $enabled = Get-WmsConfigParam -Key 'wms_gdrive.enabled' -Default '1' `
        -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
    return ($enabled -ne '0')
}

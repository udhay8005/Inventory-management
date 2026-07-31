<#
.SYNOPSIS
    Google Drive connection / upload probe with machine-readable JSON output.

.DESCRIPTION
    Backend for the WMS settings page's "Test Connection" / "Test Upload"
    buttons: wms.gdrive.settings shells out to this script and parses
    stdout. Contract (do not break it):

      - stdout carries EXACTLY ONE compact JSON line, nothing else;
      - human chatter goes to stderr (or is suppressed);
      - the script NEVER throws outward: every failure becomes
        {"ok":false,"error":"...","auth_expired":true|false} + exit 1.

    Modes:
      connection  token refresh + about.get + ensure the backup root folder.
                  -> {"ok":true,"email":"...","used_mb":...,"limit_mb":...,"folder_ok":true}
      upload      1 KB probe file into <root>/_connection_test/, verified via
                  Drive's sha256Checksum, then deleted (also in failure paths).
                  -> {"ok":true,"file":"...","roundtrip_ms":...}
      validate-folder  files.get on a caller-supplied bare folder id (the DR
                  page's "Validate Folder" button; the id is URL-parsed
                  Odoo-side and charset-validated here).
                  -> {"ok":true,"name":"...","owner":"...","accessible":true,"writable":true}

    Successful runs also refresh the wms_gdrive.last_about quota cache via
    psql (failure-safe; skipped when GDRIVE_MOCK_DIR is set so test runs
    never write to the production DB).

    GDRIVE_MOCK_DIR: honored through gdrive-lib.ps1's mock seam - all Drive
    calls operate against that local directory; OAuth client values and the
    token file are not required.

.PARAMETER Mode
    'connection' (default), 'upload' or 'validate-folder'.

.PARAMETER FolderId
    Bare Drive folder id, required by -Mode validate-folder. Charset-validated
    (^[A-Za-z0-9_-]{10,}$) so nothing dangerous reaches the API call.

.EXAMPLE
    scripts\gdrive-test.ps1 -Mode connection

.EXAMPLE
    scripts\gdrive-test.ps1 -Mode upload

.EXAMPLE
    scripts\gdrive-test.ps1 -Mode validate-folder -FolderId 1A2b3C4d5E6f7G8h9I0j

.NOTES
    Exit codes: 0 = ok:true, 1 = ok:false. No token material, passphrases,
    or client secrets ever appear in the JSON or on stderr.
#>
[CmdletBinding()]
param(
    [ValidateSet('connection', 'upload', 'validate-folder')]
    [string]$Mode = 'connection',
    # Bare Drive folder id for -Mode validate-folder. The DR page parses the id
    # out of any folder URL Odoo-side and passes ONLY the charset-validated bare
    # id here, so nothing dangerous reaches the API call. Same charset the
    # wizard's _validate() regex accepts (^[A-Za-z0-9_-]{10,}$).
    [ValidatePattern('^[A-Za-z0-9_-]{10,}$')]
    [string]$FolderId
)

$ErrorActionPreference = 'Stop'
# PS 5.1 defaults to TLS 1.0 for .NET HTTP clients; Google endpoints require 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath     = Join-Path $ProjectRoot '.env'
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'
$TokenPath   = Join-Path $ProjectRoot 'config\gdrive-token.json.dpapi'
$GdLib       = Join-Path $PSScriptRoot 'gdrive-lib.ps1'

function Write-Chatter {
    # Wizard contract: stdout belongs to the JSON line; diagnostics -> stderr.
    param([string]$Text)
    try { [Console]::Error.WriteLine($Text) } catch {}
}

function ConvertTo-GDriveId {
    # Normalize Find-/New-GDriveFolder results ($null | id string | object
    # with .id | one-element list) to a plain id string or $null.
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [object[]]) {
        if ($Value.Count -eq 0) { return $null }
        $Value = $Value[0]
    }
    if ($Value -is [string]) { return $Value }
    if ($Value.PSObject.Properties['id']) { return [string]$Value.id }
    return $null
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

# DB connection for config-param reads + the quota cache (clone of
# backup-native's odoo.native.conf resolution; all uses are failure-safe).
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
    # wms_gdrive.last_about. FAILURE-SAFE: never disturbs the JSON result.
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
        if ($LASTEXITCODE -ne 0) {
            Write-Chatter "[warn] quota cache not written (is the wms DB up?)"
        }
    } catch {
        Write-Chatter "[warn] quota cache write failed (ignored): $($_.Exception.Message)"
    }
}

$script:Result        = $null
$script:AccessToken   = $null
$script:ProbeLocal    = $null
$script:ProbeRemoteId = $null
$script:LibLoaded     = $false
$script:MockMode      = -not [string]::IsNullOrWhiteSpace($env:GDRIVE_MOCK_DIR)

try {
    # gdrive-lib functions chatter via Write-Host; streams 6/3/4 are
    # silenced around the whole block so stdout stays JSON-only. Stream 2
    # is NOT redirected here: under EAP=Stop that would turn native-command
    # stderr into terminating NativeCommandErrors (the gpg lesson).
    $null = . {
        if (-not (Test-Path -LiteralPath $GdLib)) {
            throw "gdrive-lib.ps1 not found at $GdLib"
        }
        . $GdLib
        $script:LibLoaded = $true

        $cfg = $null
        try {
            $cfg = Get-GDriveEnvConfig -EnvPath $EnvPath
        } catch {
            if (-not $script:MockMode) { throw }
            # Mock drills run without real OAuth client values in .env.
            $cfg = [pscustomobject]@{ ClientId = 'mock'; ClientSecret = 'mock'; ParentFolderId = ''; HeartbeatUrl = '' }
        }
        if (-not $script:MockMode) {
            if (-not $cfg.ClientId -or -not $cfg.ClientSecret) {
                throw "GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET are not set in .env - see docs\22-gdrive-backup.md"
            }
            if (-not (Test-Path -LiteralPath $TokenPath)) {
                throw "Google Drive is not connected - run scripts\setup-gdrive-auth.ps1 first"
            }
        }

        $script:AccessToken = Get-GDriveAccessToken -TokenPath $TokenPath -EnvConfig $cfg

        # Folder gate for connection/upload: find-or-create the backup root.
        # "Not found" is normal before the first upload, hence the create.
        # validate-folder inspects a CALLER-SUPPLIED id instead, so it does not
        # depend on (or create) the backup root.
        if ($Mode -ne 'validate-folder') {
            $folderName = Get-WmsConfigParam -Key 'wms_gdrive.folder_name' -Default 'Inventory_Backups' `
                -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
            $parentId = 'root'
            if ($cfg.ParentFolderId) { $parentId = $cfg.ParentFolderId }
            $rootId = ConvertTo-GDriveId (Find-GDriveFolder -Name $folderName -ParentId $parentId -AccessToken $script:AccessToken)
            if (-not $rootId) {
                $rootId = ConvertTo-GDriveId (New-GDriveFolder -Name $folderName -ParentId $parentId -AccessToken $script:AccessToken)
            }
            if (-not $rootId) {
                throw "could not find or create the '$folderName' folder on Drive"
            }
        }

        if ($Mode -eq 'validate-folder') {
            if (-not $FolderId) {
                throw "validate-folder requires -FolderId (a bare Drive folder id)"
            }
            $info = Get-GDriveFolderInfo -FolderId $FolderId -AccessToken $script:AccessToken
            $script:Result = [ordered]@{
                ok         = $true
                name       = [string](Get-GDriveProp $info 'name' '')
                owner      = [string](Get-GDriveProp $info 'owner' '')
                accessible = [bool](Get-GDriveProp $info 'accessible' $false)
                writable   = [bool](Get-GDriveProp $info 'writable' $false)
            }
        } elseif ($Mode -eq 'connection') {
            $sum = ConvertTo-AboutSummary (Get-GDriveAbout -AccessToken $script:AccessToken)
            $script:Result = [ordered]@{
                ok        = $true
                email     = $sum.Email
                used_mb   = $sum.UsedMb
                limit_mb  = $sum.LimitMb
                folder_ok = $true
            }
            if (-not $script:MockMode) { Write-GDriveLastAbout -Summary $sum }
        } else {
            # upload: probe file -> _connection_test/ -> sha256 verify -> delete.
            $testFolderId = ConvertTo-GDriveId (Find-GDriveFolder -Name '_connection_test' -ParentId $rootId -AccessToken $script:AccessToken)
            if (-not $testFolderId) {
                $testFolderId = ConvertTo-GDriveId (New-GDriveFolder -Name '_connection_test' -ParentId $rootId -AccessToken $script:AccessToken)
            }
            if (-not $testFolderId) {
                throw "could not find or create the '_connection_test' folder on Drive"
            }

            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $probeName = "connection-test-$stamp.txt"
            $script:ProbeLocal = Join-Path $env:TEMP $probeName
            # 1 KB ASCII probe; content is non-sensitive by construction.
            $body = "WMS Google Drive upload probe`r`nstamp: $stamp`r`nhost: $($env:COMPUTERNAME)`r`nUploaded, hash-verified, then deleted automatically by scripts\gdrive-test.ps1.`r`n"
            [System.IO.File]::WriteAllText($script:ProbeLocal, $body.PadRight(1024, '.'), [System.Text.ASCIIEncoding]::new())
            $probeHash = (Get-FileHash -LiteralPath $script:ProbeLocal -Algorithm SHA256).Hash

            # wms_probe (not wms_backup) keeps the probe invisible to the
            # retention/restore appProperties queries.
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $up = Send-GDriveFile -LocalPath $script:ProbeLocal -RemoteName $probeName -ParentId $testFolderId `
                -AppProperties @{ wms_probe = '1' } -ExpectedSha256 $probeHash -AccessToken $script:AccessToken
            $script:ProbeRemoteId = ConvertTo-GDriveId $up
            if ($script:ProbeRemoteId) {
                Remove-GDriveFile -FileId $script:ProbeRemoteId -AccessToken $script:AccessToken
                $script:ProbeRemoteId = $null
            }
            $sw.Stop()

            $script:Result = [ordered]@{
                ok           = $true
                file         = $probeName
                roundtrip_ms = [long]$sw.ElapsedMilliseconds
            }
            if (-not $script:MockMode) {
                # Quota cache refresh; about.get trouble must not fail a
                # test whose upload round-trip already succeeded.
                try {
                    Write-GDriveLastAbout -Summary (ConvertTo-AboutSummary (Get-GDriveAbout -AccessToken $script:AccessToken))
                } catch {
                    Write-Chatter "[warn] quota refresh failed (ignored): $($_.Exception.Message)"
                }
            }
        }
    } 6>$null 3>$null 4>$null
} catch {
    $msg = $_.Exception.Message
    Write-Chatter "[fail] $msg"
    $script:Result = [ordered]@{
        ok           = $false
        error        = $msg
        auth_expired = [bool]($msg -match 'GDRIVE_AUTH_EXPIRED|invalid_grant')
    }
} finally {
    # _connection_test residue is removed even on failure paths (P14).
    if ($script:ProbeRemoteId -and $script:LibLoaded -and $script:AccessToken) {
        try { $null = . { Remove-GDriveFile -FileId $script:ProbeRemoteId -AccessToken $script:AccessToken } 6>$null 3>$null 4>$null } catch {}
    }
    if ($script:ProbeLocal -and (Test-Path -LiteralPath $script:ProbeLocal)) {
        Remove-Item -LiteralPath $script:ProbeLocal -Force -ErrorAction SilentlyContinue
    }
    $script:AccessToken = $null
}

if (-not $script:Result) {
    $script:Result = [ordered]@{ ok = $false; error = 'internal: no result produced'; auth_expired = $false }
}
[Console]::Out.WriteLine((ConvertTo-Json -InputObject $script:Result -Compress -Depth 5))
if ($script:Result.ok) { exit 0 } else { exit 1 }

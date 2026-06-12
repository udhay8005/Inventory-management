#Requires -Version 5.1
<#
.SYNOPSIS
    Manager CLI for Google Drive backup sets: list the catalog, download +
    verify a set, or run the full automated restore orchestration.

.DESCRIPTION
    House policy keeps restore EXECUTION out of the web UI (the Odoo restore
    browser is read-only); this script is the only executor for
    Drive-sourced restores. Three modes:

      -List
          Render the Drive catalog as a Year > Month > Day > Time tree
          (size, type auto/manual/emergency, sha prefix, creator). Optional
          -Year/-Month/-Day filters narrow the tree.

      -SetStamp <yyyyMMdd-HHmmss>          (download only)
          Download the 4-file set (db .gpg [+ filestore .gpg] + SHA256.txt +
          backup-info.json) into -DownloadTo, verify SHA-256 with TRIPLE
          agreement (backup-info.json vs SHA256.txt vs a fresh Get-FileHash,
          plus the catalog row checksum when readable), verify the GPG
          symmetric AES256 envelope, rename Drive display names back to the
          local convention (backup-info.json name map), then print the exact
          restore-native.ps1 command to run next. Nothing is restored.

      -SetStamp <stamp> -AutoRestore -TargetDb <name>
          Full orchestration (clones the upgrade-service.ps1 skeleton):
            1. emergency pre-restore backup (backup-native.ps1
               -Source emergency -FilePrefix 'emergency-') - abort on failure
            2. download + triple verification + GPG envelope check
            3. pg_restore --list TOC gate (>= 100 entries) on the decrypted dump
            4. Stop-Service Odoo-WMS - only when the restore can collide with
               the live install: the target db is the production db, OR the
               set being restored is a backup OF the production db (its
               filestore extracts onto the live filestore folder). Scratch
               sets restored into scratch targets leave the service running.
            5. restore-native.ps1 -BackupFile <staged> -DbName <target> -Force
            6. integrity probes: res_users >= 1, ir_module_module >= 1
            7. Start-Service + /wms/health poll (36 x 5 s)
            8. restore_gdrive audit row + catalog restored_count bump + heartbeat

    PRODUCTION GUARD: restoring over the live production database ('wms')
    requires BOTH -Force AND -ConfirmTarget wms (literal typed match).
    Without them the script refuses with exit 5 and touches nothing.

    One-shot unattended runs: -AsTask registers a SYSTEM Scheduled Task
    'WMS Restore Once' firing in ~1 minute (-AtNextBoot: at next boot) that
    re-invokes this script with the resolved arguments plus -Unattended; the
    unattended run unregisters the task in its finally block. Unattended mode
    requires BACKUP_PASSPHRASE in .env (no Read-Host fallback).

    MOCK SEAM: when $env:GDRIVE_MOCK_DIR is set, list/download operate
    against that local directory end-to-end (gdrive-lib.ps1 mock seam).

.PARAMETER List          Render the catalog tree and exit.
.PARAMETER Year          -List filter, e.g. 2026.
.PARAMETER Month         -List filter: 06, 6, June or 06-June.
.PARAMETER Day           -List filter: 2026-06-12 or 12.
.PARAMETER SetStamp      Backup set id (appProperties set_id), yyyyMMdd-HHmmss.
.PARAMETER DownloadTo    Staging folder. Default <project>\backups\restore-staging.
.PARAMETER AutoRestore   Run the full restore orchestration (needs -TargetDb).
.PARAMETER TargetDb      Restore target database. REQUIRED with -AutoRestore.
.PARAMETER Force         Required (with -ConfirmTarget) when TargetDb is the
                         production database. Also forwarded conceptually:
                         restore-native always receives -Force from this script.
.PARAMETER ConfirmTarget Typed confirmation of the target db name; required
                         (literal match) when TargetDb is the production db.
.PARAMETER AsTask        Register the one-shot 'WMS Restore Once' SYSTEM task
                         (fires in ~1 minute) instead of running now.
.PARAMETER AtNextBoot    Like -AsTask but triggers at the next boot.
.PARAMETER Unattended    Set by the one-shot task. No prompts; requires
                         BACKUP_PASSPHRASE in .env; self-unregisters the task.
.PARAMETER Passphrase    Override .env BACKUP_PASSPHRASE (SecureString; not
                         forwardable across elevation or into the one-shot task).
.PARAMETER DbHost        Postgres host override (default: odoo.native.conf).
.PARAMETER DbPort        Postgres port override.
.PARAMETER DbUser        Postgres user override.
.PARAMETER CatalogDb     Database hosting the wms_reports bookkeeping tables
                         (wms_backup_audit / wms_gdrive_backup) - audit rows,
                         catalog reads/bumps AND the emergency pre-restore
                         backup target. Default: the production db ('wms').
                         Test/E2E runs point this at a scratch clone so the
                         production db stays untouched (spec test plan
                         12(b).6 read-only constraint).

.EXAMPLE
    scripts\gdrive-restore.ps1 -List
.EXAMPLE
    scripts\gdrive-restore.ps1 -SetStamp 20260612-163000
.EXAMPLE
    scripts\gdrive-restore.ps1 -SetStamp 20260612-163000 -AutoRestore -TargetDb wms_restore_20260612_163000
.EXAMPLE
    scripts\gdrive-restore.ps1 -SetStamp 20260612-163000 -AutoRestore -TargetDb wms -Force -ConfirmTarget wms
.EXAMPLE
    scripts\gdrive-restore.ps1 -SetStamp 20260612-163000 -AutoRestore -TargetDb wms_restore_x -AsTask

.NOTES
    Exit codes (restore-drill house pattern; Event Log id = 400 + code):
      0 OK   1 SET_NOT_FOUND   2 DOWNLOAD_FAILED   3 VERIFY_FAILED
      4 RESTORE_FAILED   5 PROD_GUARD   6 AUTH_EXPIRED
    Logs: .runtime\logs\gdrive-restore.log + best-effort Event Log source
    'WMS_Backup_Drill' (registered once by the drill setup; skipped if absent).
#>
[CmdletBinding()]
param(
    [switch]$List,
    [string]$Year,
    [string]$Month,
    [string]$Day,
    [string]$SetStamp,
    [string]$DownloadTo,
    [switch]$AutoRestore,
    [string]$TargetDb,
    [switch]$Force,
    [string]$ConfirmTarget,
    [switch]$AsTask,
    [switch]$AtNextBoot,
    [switch]$Unattended,
    [SecureString]$Passphrase,
    [string]$DbHost,
    [int]$DbPort,
    [string]$DbUser,
    [string]$CatalogDb
)

$ErrorActionPreference = 'Stop'
$ProjectRoot   = Split-Path -Parent $PSScriptRoot
$EnvPath       = Join-Path $ProjectRoot '.env'
$ConfPath      = Join-Path $ProjectRoot 'config\odoo.native.conf'
$TokenPath     = Join-Path $ProjectRoot 'config\gdrive-token.json.dpapi'
$BackupNative  = Join-Path $ProjectRoot 'scripts\backup-native.ps1'
$RestoreNative = Join-Path $ProjectRoot 'scripts\restore-native.ps1'
$LogDir        = Join-Path $ProjectRoot '.runtime\logs'
$LogFile       = Join-Path $LogDir 'gdrive-restore.log'

# Live production database + service constants. The guard compares
# case-INsensitively because unquoted Postgres identifiers fold to lowercase
# (a -TargetDb WMS would still drop the real wms).
$ProdDbName   = 'wms'
$ServiceName  = 'Odoo-WMS'
$OnceTaskName = 'WMS Restore Once'

# Named exit codes (restore-drill house pattern).
$EXIT_OK              = 0
$EXIT_SET_NOT_FOUND   = 1
$EXIT_DOWNLOAD_FAILED = 2
$EXIT_VERIFY_FAILED   = 3
$EXIT_RESTORE_FAILED  = 4
$EXIT_PROD_GUARD      = 5
$EXIT_AUTH_EXPIRED    = 6

# Remember whether the operator chose a staging dir BEFORE we fill the
# default (the one-shot task only forwards explicitly-given arguments).
$DownloadToGiven = [bool]$DownloadTo
if (-not $DownloadTo) { $DownloadTo = Join-Path $ProjectRoot 'backups\restore-staging' }
$CatalogDbGiven = [bool]$CatalogDb

# --- Logging: dual sink - file + best-effort Windows Event Log ------------
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-RestoreLog {
    param(
        [Parameter(Mandatory)] [string]$Level,
        [Parameter(Mandatory)] [string]$Message
    )
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$stamp] [$Level] $Message"
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8 } catch { }
    $color = switch ($Level) {
        'ERROR' { 'Red' }
        'WARN'  { 'Yellow' }
        'OK'    { 'Green' }
        'STEP'  { 'Cyan' }
        default { 'Gray' }
    }
    Write-Host $line -ForegroundColor $color
}

function Write-RestoreEvent {
    # Best-effort Application Event Log entry, reusing the WMS_Backup_Drill
    # source the drill registers. Id 400 = success, 400 + exit code = failure.
    param(
        [Parameter(Mandatory)] [int]$EventId,
        [Parameter(Mandatory)] [ValidateSet('Information','Warning','Error')] [string]$EntryType,
        [Parameter(Mandatory)] [string]$Message
    )
    try {
        if ([System.Diagnostics.EventLog]::SourceExists('WMS_Backup_Drill')) {
            Write-EventLog -LogName Application -Source 'WMS_Backup_Drill' `
                -EntryType $EntryType -EventId $EventId -Message $Message
        }
    } catch {
        Write-RestoreLog 'WARN' "Event Log write skipped: $($_.Exception.Message)"
    }
}

# --- Usage validation ------------------------------------------------------
if (-not $List -and -not $SetStamp) {
    Write-Host 'Nothing to do. Use -List, or -SetStamp <yyyyMMdd-HHmmss> [-AutoRestore -TargetDb <name>].' -ForegroundColor Red
    Write-Host 'See: Get-Help scripts\gdrive-restore.ps1 -Full' -ForegroundColor Yellow
    exit 1
}
if ($SetStamp -and $SetStamp -notmatch '^\d{8}-\d{6}$') {
    Write-Host "Invalid -SetStamp '$SetStamp' (expected yyyyMMdd-HHmmss, e.g. 20260612-163000)." -ForegroundColor Red
    exit 1
}
if ($AutoRestore -and -not $TargetDb) {
    Write-Host '-AutoRestore requires -TargetDb <database name> (use a scratch name like wms_restore_<stamp> for drills).' -ForegroundColor Red
    exit 1
}
if (($AsTask -or $AtNextBoot) -and -not $SetStamp) {
    Write-Host '-AsTask / -AtNextBoot need -SetStamp (and usually -AutoRestore -TargetDb ...).' -ForegroundColor Red
    exit 1
}

# --- PRODUCTION GUARD (before anything else touches the box) ---------------
# Restoring over the live db requires a deliberate, typed double confirmation.
if ($AutoRestore -and $TargetDb -and ($TargetDb -ieq $ProdDbName)) {
    $confirmOk = ($Force -and ($ConfirmTarget -ceq $TargetDb))
    if (-not $confirmOk) {
        Write-RestoreLog 'ERROR' "PROD GUARD: refusing to restore over the LIVE production database '$ProdDbName'."
        Write-Host ''
        Write-Host '  This would DROP and replace the live WMS database and filestore.' -ForegroundColor Red
        Write-Host '  If you really mean it, pass BOTH safety switches, typed exactly:' -ForegroundColor Yellow
        Write-Host "      scripts\gdrive-restore.ps1 -SetStamp $SetStamp -AutoRestore -TargetDb $TargetDb -Force -ConfirmTarget $TargetDb" -ForegroundColor Yellow
        Write-Host '  An emergency pre-restore backup is still taken first, but do not' -ForegroundColor Yellow
        Write-Host '  run this against production outside a planned maintenance window.' -ForegroundColor Yellow
        Write-RestoreEvent -EventId (400 + $EXIT_PROD_GUARD) -EntryType Error `
            -Message "gdrive-restore prod guard refused -TargetDb $TargetDb without -Force -ConfirmTarget $TargetDb (set $SetStamp). Nothing touched."
        exit $EXIT_PROD_GUARD
    }
    Write-RestoreLog 'WARN' "PROD GUARD passed: -Force -ConfirmTarget '$ConfirmTarget' authorizes a restore over '$ProdDbName'."
}

# --- Self-elevate (interactive admin path, upgrade-service.ps1 skeleton) ---
# Service stop/start and SYSTEM task registration need admin. List and
# download-only runs do not.
if (($AutoRestore -or $AsTask -or $AtNextBoot) -and -not $Unattended) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host 'Administrator rights required - relaunching elevated (approve the UAC prompt)...' -ForegroundColor Yellow
        if ($Passphrase) {
            Write-Host '  (-Passphrase cannot cross the elevation boundary; the elevated run re-reads .env or prompts.)' -ForegroundColor DarkGray
        }
        $relaunch = @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
            '-File', ('"{0}"' -f $PSCommandPath), '-SetStamp', $SetStamp)
        if ($AutoRestore)     { $relaunch += @('-AutoRestore', '-TargetDb', $TargetDb) }
        if ($Force)           { $relaunch += '-Force' }
        if ($ConfirmTarget)   { $relaunch += @('-ConfirmTarget', $ConfirmTarget) }
        if ($AsTask)          { $relaunch += '-AsTask' }
        if ($AtNextBoot)      { $relaunch += '-AtNextBoot' }
        if ($DownloadToGiven) { $relaunch += @('-DownloadTo', ('"{0}"' -f $DownloadTo)) }
        if ($DbHost)          { $relaunch += @('-DbHost', $DbHost) }
        if ($DbPort)          { $relaunch += @('-DbPort', "$DbPort") }
        if ($DbUser)          { $relaunch += @('-DbUser', $DbUser) }
        if ($CatalogDbGiven)  { $relaunch += @('-CatalogDb', $CatalogDb) }
        Start-Process powershell.exe -Verb RunAs -ArgumentList $relaunch
        return
    }
}

# --- Library ----------------------------------------------------------------
$GdLib = Join-Path $PSScriptRoot 'gdrive-lib.ps1'
if (-not (Test-Path -LiteralPath $GdLib)) {
    Write-RestoreLog 'ERROR' "gdrive-lib.ps1 not found next to this script ($GdLib)."
    exit $EXIT_DOWNLOAD_FAILED
}
. $GdLib

# Resolved Postgres connection for audit/catalog/probe psql calls. Audit and
# catalog rows target the db where wms_reports lives - the production wms db
# by default, or -CatalogDb (scratch E2E runs, spec 12(b).6 keeps prod
# read-only under test); probes use the same host/port/user against -TargetDb.
if (-not $CatalogDb) { $CatalogDb = $ProdDbName }
$script:Conn = Resolve-WmsDbConnection -DbName $CatalogDb -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser

# Heartbeat URL (HEALTHCHECK_GDRIVE_URL, shared with backup Stage 5).
# Failure-safe: a broken .env must not block a -List.
$script:HeartbeatUrl = ''
$script:EnvCfg = $null
try {
    $script:EnvCfg = Get-GDriveEnvConfig -EnvPath $EnvPath
    $script:HeartbeatUrl = $script:EnvCfg.HeartbeatUrl
} catch {
    Write-RestoreLog 'WARN' "Drive .env config problem (continuing): $($_.Exception.Message)"
    $script:EnvCfg = [pscustomobject]@{ ClientId = ''; ClientSecret = ''; ParentFolderId = ''; HeartbeatUrl = '' }
}

function Send-Heartbeat {
    # Non-blocking 10 s ping; /fail suffix signals failure. Silent on error -
    # observability must never break the restore.
    param([string]$Url, [switch]$Fail)
    if (-not $Url) { return }
    $target = if ($Fail) { "$Url/fail" } else { $Url }
    try {
        Invoke-WebRequest -Uri $target -Method Get -TimeoutSec 10 -UseBasicParsing | Out-Null
    } catch {
        Write-RestoreLog 'WARN' "Heartbeat ping failed (ignored): $($_.Exception.Message)"
    }
}

function Write-RestoreAudit {
    # One restore_gdrive row in wms_backup_audit via psql. FAILURE-SAFE
    # (Write-BackupAudit clone): a down DB degrades to a DarkGray note.
    param(
        [bool]$Success, [string]$FileName, [double]$SizeMb = 0,
        [int]$TocEntries = 0, [bool]$Verified = $false,
        [double]$DurationSeconds = 0, [string]$Checksum = '', [string]$Message = ''
    )
    try {
        $sk = if ($Success)  { 'true' } else { 'false' }
        $vf = if ($Verified) { 'true' } else { 'false' }
        $fn  = ($FileName -replace "'", "''")
        $msg = ($Message  -replace "'", "''")
        $cs  = ($Checksum -replace "'", "''")
        $hn  = ($env:COMPUTERNAME -replace "'", "''")
        $dur = [System.Convert]::ToString([math]::Round($DurationSeconds, 1), [System.Globalization.CultureInfo]::InvariantCulture)
        $smb = [System.Convert]::ToString($SizeMb, [System.Globalization.CultureInfo]::InvariantCulture)
        $sql = "INSERT INTO wms_backup_audit (name, audit_type, success, event_time, duration_seconds, size_mb, toc_entries, verified, checksum, host, message, create_uid, create_date, write_uid, write_date) VALUES ('$fn', 'restore_gdrive', $sk, NOW(), $dur, $smb, $TocEntries, $vf, '$cs', '$hn', '$msg', 1, NOW(), 1, NOW());"
        $sql | & psql -U $script:Conn.DbUser -h $script:Conn.DbHost -p $script:Conn.DbPort -d $script:Conn.DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host '    [audit] recorded restore_gdrive in wms_backup_audit' -ForegroundColor DarkGray
        } else {
            Write-Host '    [warn] restore audit not recorded (is wms_reports installed?)' -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] restore audit write failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Update-RestoredCount {
    # Bump wms_gdrive_backup.restored_count for the set (failure-safe).
    param([Parameter(Mandatory)] [string]$Stamp)
    try {
        $esc = ($Stamp -replace "'", "''")
        # COALESCE: catalog rows written via psql (Write-GDriveCatalogRow) carry
        # NULL restored_count (no ORM default there), and NULL + 1 stays NULL.
        $sql = "UPDATE wms_gdrive_backup SET restored_count = COALESCE(restored_count, 0) + 1, write_uid = 1, write_date = NOW() WHERE set_stamp = '$esc';"
        $sql | & psql -U $script:Conn.DbUser -h $script:Conn.DbHost -p $script:Conn.DbPort -d $script:Conn.DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host '    [audit] bumped restored_count in wms_gdrive_backup' -ForegroundColor DarkGray
        } else {
            Write-Host '    [warn] restored_count not bumped (catalog unreadable - ignored)' -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] restored_count bump failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Exit-RestoreFail {
    # Single failure funnel: log + Event Log (400 + code) + optional failed
    # audit row + /fail heartbeat, then exit with the named code.
    param(
        [Parameter(Mandatory)] [int]$Code,
        [Parameter(Mandatory)] [string]$Message,
        [string]$AuditFile = ''
    )
    Write-RestoreLog 'ERROR' $Message
    Write-RestoreEvent -EventId (400 + $Code) -EntryType Error -Message "gdrive-restore: $Message"
    if ($AuditFile) {
        Write-RestoreAudit -Success $false -FileName $AuditFile -Message $Message
    }
    Send-Heartbeat -Url $script:HeartbeatUrl -Fail
    exit $Code
}

function Get-CatalogSetMap {
    # set_stamp -> creator/checksum from the wms_gdrive_backup catalog
    # (failure-safe: empty map when the DB or table is unreachable).
    $map = @{ }
    try {
        $rows = & psql -U $script:Conn.DbUser -h $script:Conn.DbHost -p $script:Conn.DbPort -d $script:Conn.DbName -w -t -A `
            -v ON_ERROR_STOP=1 -c "SELECT set_stamp, COALESCE(creator,''), COALESCE(checksum,'') FROM wms_gdrive_backup WHERE set_stamp IS NOT NULL;" 2>$null
        if ($LASTEXITCODE -ne 0) { return $map }
        foreach ($r in @($rows)) {
            if (-not $r) { continue }
            $parts = "$r" -split '\|', 3
            if ($parts.Count -ge 1 -and $parts[0]) {
                $creator = ''
                $checksum = ''
                if ($parts.Count -ge 2) { $creator = $parts[1] }
                if ($parts.Count -ge 3) { $checksum = $parts[2] }
                $map[$parts[0].Trim()] = @{ creator = $creator; checksum = $checksum }
            }
        }
    } catch { }
    return $map
}

function Resolve-GpgPath {
    $gpgCmd = Get-Command gpg.exe -ErrorAction SilentlyContinue
    if ($gpgCmd) { return $gpgCmd.Source }
    foreach ($cand in @(
        'C:\Program Files (x86)\GnuPG\bin\gpg.exe',
        'C:\Program Files\GnuPG\bin\gpg.exe'
    )) { if (Test-Path $cand) { return $cand } }
    return $null
}

function Test-GpgSymmetricEnvelope {
    # Verify the artifact is a GPG SYMMETRIC AES256 envelope by running
    # gpg --list-packets over the FIRST bytes only (the symkey packet leads
    # the stream; no passphrase needed to see it). cmd /c shim because gpg is
    # stderr-noisy and PS 5.1 + $ErrorActionPreference=Stop treats that as
    # fatal. Throws a reason string on failure.
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$GpgExe
    )
    $head = Join-Path $env:TEMP ('wms-gdrive-restore-head-' + [guid]::NewGuid().ToString('N') + '.gpg')
    $outFile = [System.IO.Path]::GetTempFileName()
    try {
        $fs = [System.IO.File]::OpenRead($Path)
        try {
            $len = [int][Math]::Min(16384, $fs.Length)
            $buf = New-Object byte[] $len
            $read = 0
            while ($read -lt $len) {
                $n = $fs.Read($buf, $read, $len - $read)
                if ($n -le 0) { break }
                $read += $n
            }
        } finally { $fs.Dispose() }
        [System.IO.File]::WriteAllBytes($head, $buf)
        # Exit code is meaningless on a truncated stream - parse the packet
        # dump instead. Cipher algo 9 = AES256. --pinentry-mode cancel is
        # REQUIRED: gpg 2.x tries to decrypt the symmetric session key while
        # listing packets and --batch alone does NOT stop the agent from
        # popping a GUI pinentry (the prompt would hang unattended runs);
        # 'cancel' auto-dismisses it AFTER the symkey packet line - the only
        # thing we parse - has already been printed.
        $cmd = '"' + $GpgExe + '" --batch --pinentry-mode cancel --list-packets "' + $head + '" > "' + $outFile + '" 2>&1'
        & cmd /c $cmd | Out-Null
        $text = ''
        if (Test-Path -LiteralPath $outFile) {
            $text = Get-Content -LiteralPath $outFile -Raw -ErrorAction SilentlyContinue
        }
        if (-not $text -or $text -notmatch ':symkey enc packet:') {
            throw "no GPG symmetric-key packet found in $(Split-Path -Leaf $Path) - not a passphrase-encrypted backup artifact"
        }
        if ($text -notmatch ':symkey enc packet:[^\r\n]*cipher\s+9\b') {
            throw "GPG envelope of $(Split-Path -Leaf $Path) is not AES256 (expected cipher algo 9)"
        }
    } finally {
        Remove-Item -LiteralPath $head, $outFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-GpgDecrypt {
    # restore-native.ps1's decrypt helper, cloned: passphrase via a
    # short-lived FILE (cmd metacharacter-safe), gpg via cmd /c so agent
    # start-up stderr cannot become a fatal NativeCommandError.
    param(
        [Parameter(Mandatory)] [SecureString]$Pass,
        [Parameter(Mandatory)] [string]$InputFile,
        [Parameter(Mandatory)] [string]$OutputFile,
        [Parameter(Mandatory)] [string]$GpgExe
    )
    $errFile = [System.IO.Path]::GetTempFileName()
    $pwFile  = [System.IO.Path]::GetTempFileName()
    $plain = $null
    try {
        $plain = [System.Net.NetworkCredential]::new('', $Pass).Password
        [System.IO.File]::WriteAllBytes($pwFile, [System.Text.Encoding]::UTF8.GetBytes($plain))
        $cmd = '"' + $GpgExe + '" --batch --yes --pinentry-mode loopback ' +
               '--passphrase-file "' + $pwFile + '" ' +
               '--decrypt -o "' + $OutputFile + '" "' + $InputFile + '" ' +
               '2> "' + $errFile + '"'
        & cmd /c $cmd
        $rc = $LASTEXITCODE
        if ($rc -ne 0) {
            $stderr = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
            throw "gpg decryption failed (exit $rc) on $InputFile. Wrong passphrase?`n$stderr"
        }
    } finally {
        $plain = $null
        if (Test-Path -LiteralPath $pwFile) {
            try { [System.IO.File]::WriteAllBytes($pwFile, (New-Object byte[] 64)) } catch { }
            Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-DriveAccessTokenOrExit {
    $af = ''
    if ($SetStamp) { $af = "set-$SetStamp" }
    try {
        return Get-GDriveAccessToken -TokenPath $TokenPath -EnvConfig $script:EnvCfg
    } catch {
        $m = $_.Exception.Message
        if ($m -match 'GDRIVE_AUTH_EXPIRED') {
            Exit-RestoreFail -Code $EXIT_AUTH_EXPIRED -Message $m -AuditFile $af
        }
        Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "Drive access unavailable: $m"
    }
}

# === -List: Year > Month > Day > Time catalog tree =========================

function Show-GDriveBackupTree {
    $tok = Get-DriveAccessTokenOrExit
    $files = @()
    try {
        $files = @(Get-GDriveBackupSets -AccessToken $tok)
    } catch {
        $m = $_.Exception.Message
        if ($m -match 'GDRIVE_AUTH_EXPIRED') { Exit-RestoreFail -Code $EXIT_AUTH_EXPIRED -Message $m }
        Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "Drive listing failed: $m"
    }
    $catalog = Get-CatalogSetMap

    # Group flat files into sets keyed by appProperties.set_id.
    $sets = @{ }
    foreach ($f in $files) {
        $props = Get-GDriveProp $f 'appProperties' $null
        $sid = [string](Get-GDriveProp $props 'set_id' '')
        if (-not $sid) { continue }
        if (-not $sets.ContainsKey($sid)) {
            $sets[$sid] = @{ Stamp = $sid; Type = [string](Get-GDriveProp $props 'backup_type' 'auto');
                             Bytes = [long]0; HasDb = $false; MockSha = '' }
        }
        $role = [string](Get-GDriveProp $props 'role' '')
        if ($role -eq 'db' -or $role -eq 'filestore') {
            $sets[$sid].Bytes += [long](Get-GDriveProp $f 'size' 0)
        }
        if ($role -eq 'db') {
            $sets[$sid].HasDb = $true
            $sets[$sid].MockSha = [string](Get-GDriveProp $f 'sha256Checksum' '')
        }
    }

    Write-Host ''
    Write-Host 'Google Drive backup catalog (Year > Month > Day > Time)' -ForegroundColor Cyan
    if (Test-GDriveMock) { Write-Host "  [mock mode: GDRIVE_MOCK_DIR=$env:GDRIVE_MOCK_DIR]" -ForegroundColor DarkGray }
    if ($Year -or $Month -or $Day) { Write-Host "  filters: Year=$Year Month=$Month Day=$Day" -ForegroundColor DarkGray }

    $shown = 0
    $curYear = ''; $curMonth = ''; $curDay = ''
    foreach ($s in ($sets.Values | Sort-Object -Property @{ Expression = { $_.Stamp } } -Descending)) {
        $d = $null
        try {
            $d = [datetime]::ParseExact($s.Stamp, 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture)
        } catch { continue }
        $yLabel = $d.ToString('yyyy')
        $mLabel = '{0:00}-{1}' -f $d.Month, [System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($d.Month)
        $dLabel = $d.ToString('yyyy-MM-dd')

        if ($Year -and ($yLabel -ne $Year)) { continue }
        if ($Month) {
            $mNum = 0
            $mOk = ($mLabel -ieq $Month) -or
                   ([System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($d.Month) -ieq $Month) -or
                   ([int]::TryParse($Month, [ref]$mNum) -and $mNum -eq $d.Month)
            if (-not $mOk) { continue }
        }
        if ($Day) {
            $dNum = 0
            $dOk = ($dLabel -eq $Day) -or ([int]::TryParse($Day, [ref]$dNum) -and $dNum -eq $d.Day)
            if (-not $dOk) { continue }
        }

        if ($yLabel -ne $curYear)  { Write-Host $yLabel -ForegroundColor Cyan;            $curYear = $yLabel; $curMonth = ''; $curDay = '' }
        if ($mLabel -ne $curMonth) { Write-Host "  $mLabel" -ForegroundColor White;        $curMonth = $mLabel; $curDay = '' }
        if ($dLabel -ne $curDay)   { Write-Host "    $dLabel" -ForegroundColor White;      $curDay = $dLabel }

        $sizeMb = [math]::Round($s.Bytes / 1MB, 1)
        $sha = ''
        $creator = ''
        if ($catalog.ContainsKey($s.Stamp)) {
            $sha = [string]$catalog[$s.Stamp].checksum
            $creator = [string]$catalog[$s.Stamp].creator
        }
        if (-not $sha -and $s.MockSha) { $sha = $s.MockSha }
        $shaPrefix = '-'
        if ($sha) { $shaPrefix = $sha.Substring(0, [Math]::Min(12, $sha.Length)).ToLowerInvariant() }
        if (-not $creator) { $creator = '-' }
        $note = ''
        if (-not $s.HasDb) { $note = '  [INCOMPLETE: db file missing]' }
        $line = '      {0}  {1,-10} {2,8} MB  sha {3,-12}  set {4}  creator {5}{6}' -f `
            $d.ToString('HH:mm:ss'), $s.Type, $sizeMb, $shaPrefix, $s.Stamp, $creator, $note
        $fg = 'Gray'
        if ($s.Type -ne 'auto') { $fg = 'Yellow' }
        Write-Host $line -ForegroundColor $fg
        $shown++
    }

    Write-Host ''
    if ($shown -eq 0) {
        Write-Host 'No backup sets found on Drive (matching the filters).' -ForegroundColor Yellow
    } else {
        Write-Host "$shown set(s) listed." -ForegroundColor Green
        Write-Host '  download : scripts\gdrive-restore.ps1 -SetStamp <set>' -ForegroundColor DarkGray
        Write-Host '  restore  : scripts\gdrive-restore.ps1 -SetStamp <set> -AutoRestore -TargetDb wms_restore_<set>' -ForegroundColor DarkGray
    }
}

# === One-shot task registration ============================================

function Register-RestoreOnceTask {
    Write-RestoreLog 'STEP' "Registering one-shot task '$OnceTaskName' (SYSTEM, self-unregistering)."
    $taskArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath), '-SetStamp', $SetStamp)
    if ($AutoRestore)     { $taskArgs += @('-AutoRestore', '-TargetDb', $TargetDb) }
    if ($Force)           { $taskArgs += '-Force' }
    if ($ConfirmTarget)   { $taskArgs += @('-ConfirmTarget', $ConfirmTarget) }
    if ($DownloadToGiven) { $taskArgs += @('-DownloadTo', ('"{0}"' -f $DownloadTo)) }
    if ($DbHost)          { $taskArgs += @('-DbHost', $DbHost) }
    if ($DbPort)          { $taskArgs += @('-DbPort', "$DbPort") }
    if ($DbUser)          { $taskArgs += @('-DbUser', $DbUser) }
    if ($CatalogDbGiven)  { $taskArgs += @('-CatalogDb', $CatalogDb) }
    $taskArgs += '-Unattended'

    # Unattended runs cannot Read-Host: warn now if .env lacks the passphrase.
    $ppLine = $null
    if (Test-Path $EnvPath) {
        $ppLine = Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1
    }
    if ($AutoRestore -and -not $ppLine) {
        Write-RestoreLog 'WARN' 'BACKUP_PASSPHRASE is not set in .env - the unattended run WILL fail. Add it before the trigger fires.'
    }

    if ($AtNextBoot) {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $when = 'at the next boot'
    } else {
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
        $when = 'in ~1 minute'
    }
    $principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' `
        -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ($taskArgs -join ' ') -WorkingDirectory $ProjectRoot
    Register-ScheduledTask -TaskName $OnceTaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal `
        -Description "One-shot Google Drive restore (set $SetStamp). Registered by gdrive-restore.ps1; the run unregisters this task in its finally block." `
        -Force | Out-Null
    Write-RestoreLog 'OK' "Registered '$OnceTaskName' - fires $when. Progress: .runtime\logs\gdrive-restore.log"
    Write-Host "  cancel with: Unregister-ScheduledTask -TaskName '$OnceTaskName' -Confirm:`$false" -ForegroundColor DarkGray
}

# === Download + verification ===============================================

function Invoke-GDriveSetDownload {
    # Fetch the 4-file set into the staging dir, enforce TRIPLE sha-256
    # agreement (backup-info.json vs SHA256.txt vs fresh Get-FileHash; plus
    # the catalog checksum when readable), verify the GPG AES256 envelope and
    # rename Drive display names back to the local convention. Returns a
    # summary object; exits via Exit-RestoreFail on any problem.
    param(
        [Parameter(Mandatory)] [string]$Stamp,
        [Parameter(Mandatory)] [string]$Staging,
        [Parameter(Mandatory)] [string]$GpgExe
    )
    $auditName = "set-$Stamp"
    $tok = Get-DriveAccessTokenOrExit

    Write-RestoreLog 'STEP' "Locating set $Stamp on Drive..."
    $setFiles = @()
    try {
        $escStamp = ConvertTo-GDriveQueryLiteral $Stamp
        $setFiles = @(Get-GDriveBackupSets -AccessToken $tok `
            -ExtraQ (" and appProperties has {{ key='set_id' and value='{0}' }}" -f $escStamp))
    } catch {
        $m = $_.Exception.Message
        if ($m -match 'GDRIVE_AUTH_EXPIRED') { Exit-RestoreFail -Code $EXIT_AUTH_EXPIRED -Message $m -AuditFile $auditName }
        Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "Drive query for set $Stamp failed: $m" -AuditFile $auditName
    }
    if ($setFiles.Count -eq 0) {
        Exit-RestoreFail -Code $EXIT_SET_NOT_FOUND `
            -Message "No backup set with stamp $Stamp found on Drive (check scripts\gdrive-restore.ps1 -List)." `
            -AuditFile $auditName
    }

    # Classify by appProperties.role (names may carry _HH-MM-SS suffixes).
    $byRole = @{ }
    foreach ($f in $setFiles) {
        $role = [string](Get-GDriveProp (Get-GDriveProp $f 'appProperties' $null) 'role' '')
        if ($role -and -not $byRole.ContainsKey($role)) { $byRole[$role] = $f }
    }
    foreach ($need in @('db', 'sha256', 'info')) {
        if (-not $byRole.ContainsKey($need)) {
            Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED `
                -Message "Set $Stamp is incomplete on Drive: missing the '$need' file. Re-upload via the pending sweep or pick another set." `
                -AuditFile $auditName
        }
    }

    New-Item -ItemType Directory -Force -Path $Staging | Out-Null

    # 1. Sidecars first (small; they define names + expected hashes).
    $infoPath = Join-Path $Staging "backup-info_$Stamp.json"
    $shaPath  = Join-Path $Staging "SHA256_$Stamp.txt"
    try {
        Receive-GDriveFile -FileId ([string]$byRole['info'].id) -OutPath $infoPath -AccessToken $tok | Out-Null
        Receive-GDriveFile -FileId ([string]$byRole['sha256'].id) -OutPath $shaPath -AccessToken $tok | Out-Null
    } catch {
        Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "Sidecar download failed for set ${Stamp}: $($_.Exception.Message)" -AuditFile $auditName
    }

    $info = $null
    try { $info = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json } catch {
        Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "backup-info.json of set $Stamp is unreadable: $($_.Exception.Message)" -AuditFile $auditName
    }
    $infoStamp = [string](Get-GDriveProp $info 'set_stamp' '')
    if ($infoStamp -ne $Stamp) {
        Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "backup-info.json set_stamp '$infoStamp' does not match requested set $Stamp." -AuditFile $auditName
    }

    # SHA256.txt: '<64-hex>  <drive name>' per line, keyed by Drive name.
    $shaMap = @{ }
    foreach ($line in @(Get-Content -LiteralPath $shaPath -ErrorAction SilentlyContinue)) {
        if ("$line" -match '^([0-9a-fA-F]{64})\s+(.+)$') {
            $shaMap[$Matches[2].Trim()] = $Matches[1].ToLowerInvariant()
        }
    }

    $catalog = Get-CatalogSetMap

    $result = [ordered]@{
        DbPath = ''; DbSha = ''; DbLeaf = ''; FsPath = ''; FsSha = ''
        SizeMb = 0.0; TocEntries = [int](Get-GDriveProp $info 'toc_entries' 0)
        BackupType = [string](Get-GDriveProp $info 'backup_type' 'auto')
        DbName = [string](Get-GDriveProp $info 'db_name' '')
        InfoPath = $infoPath
    }

    foreach ($entry in @(Get-GDriveProp $info 'files' @())) {
        $role      = [string](Get-GDriveProp $entry 'role' '')
        $localName = [string](Get-GDriveProp $entry 'local_name' '')
        $driveName = [string](Get-GDriveProp $entry 'drive_name' '')
        $wantSha   = ([string](Get-GDriveProp $entry 'sha256' '')).ToLowerInvariant()
        $wantSize  = [long](Get-GDriveProp $entry 'size_bytes' 0)
        if ($role -ne 'db' -and $role -ne 'filestore') { continue }
        if (-not $localName -or $localName -match '[\\/]') {
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "backup-info.json carries an unusable local_name '$localName' for the $role file." -AuditFile $auditName
        }
        if (-not $wantSha -or $wantSha.Length -ne 64) {
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "backup-info.json carries no usable sha256 for $driveName." -AuditFile $auditName
        }

        # Agreement 1: backup-info.json vs SHA256.txt (before any big download).
        if (-not $shaMap.ContainsKey($driveName)) {
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "SHA256.txt of set $Stamp has no line for $driveName - sidecars disagree." -AuditFile $auditName
        }
        if ($shaMap[$driveName] -ne $wantSha) {
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED `
                -Message "Checksum disagreement for ${driveName}: backup-info.json=$wantSha SHA256.txt=$($shaMap[$driveName])." -AuditFile $auditName
        }
        # Agreement 1b (db only): catalog row checksum, when readable.
        if ($role -eq 'db' -and $catalog.ContainsKey($Stamp)) {
            $catSha = ([string]$catalog[$Stamp].checksum).ToLowerInvariant()
            if ($catSha -and $catSha -ne $wantSha) {
                Exit-RestoreFail -Code $EXIT_VERIFY_FAILED `
                    -Message "Catalog checksum for set $Stamp ($catSha) disagrees with backup-info.json ($wantSha)." -AuditFile $auditName
            }
        }

        if (-not $byRole.ContainsKey($role)) {
            Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "backup-info.json lists a $role file but Drive has none for set $Stamp." -AuditFile $auditName
        }

        # 2. Download under the LOCAL name (the rename per the D8 name map).
        $outPath = Join-Path $Staging $localName
        Write-RestoreLog 'STEP' "Downloading $driveName -> $localName"
        try {
            Receive-GDriveFile -FileId ([string]$byRole[$role].id) -OutPath $outPath `
                -ExpectedSha256 $wantSha -AccessToken $tok | Out-Null
        } catch {
            $m = $_.Exception.Message
            if ($m -match 'SHA-256 verification') {
                Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "Downloaded $driveName failed SHA-256 verification: $m" -AuditFile $localName
            }
            Exit-RestoreFail -Code $EXIT_DOWNLOAD_FAILED -Message "Download of $driveName failed: $m" -AuditFile $localName
        }

        # Agreement 2+3: fresh Get-FileHash of the staged bytes vs both sidecars.
        $fresh = (Get-FileHash -LiteralPath $outPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($fresh -ne $wantSha) {
            Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED `
                -Message "Staged $localName hash $fresh does not match the recorded $wantSha (corrupt download deleted)." -AuditFile $localName
        }
        $actualSize = (Get-Item -LiteralPath $outPath).Length
        if ($wantSize -gt 0 -and $actualSize -ne $wantSize) {
            Remove-Item -LiteralPath $outPath -Force -ErrorAction SilentlyContinue
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED `
                -Message "Staged $localName is $actualSize bytes, backup-info.json says $wantSize (corrupt download deleted)." -AuditFile $localName
        }

        # 3. GPG symmetric AES256 envelope check (first bytes, cmd /c shim).
        try {
            Test-GpgSymmetricEnvelope -Path $outPath -GpgExe $GpgExe
        } catch {
            Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "GPG envelope check failed: $($_.Exception.Message)" -AuditFile $localName
        }
        Write-RestoreLog 'OK' ('verified {0} (sha256 {1}..., {2} MB, GPG AES256 envelope)' -f `
            $localName, $fresh.Substring(0, 12), [math]::Round($actualSize / 1MB, 2))

        if ($role -eq 'db') {
            $result.DbPath = $outPath; $result.DbSha = $wantSha; $result.DbLeaf = $localName
            $result.SizeMb = [math]::Round($actualSize / 1MB, 2)
        } else {
            $result.FsPath = $outPath; $result.FsSha = $wantSha
        }
    }

    if (-not $result.DbPath) {
        Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "backup-info.json of set $Stamp lists no db artifact - nothing restorable." -AuditFile $auditName
    }
    if (-not $result.FsPath) {
        Write-RestoreLog 'WARN' 'Set carries no filestore artifact (filestore stage was skipped at backup time).'
    }
    return [pscustomobject]$result
}

# === Main ====================================================================

try {
    if ($List) {
        Show-GDriveBackupTree
        exit $EXIT_OK
    }

    if ($AsTask -or $AtNextBoot) {
        Register-RestoreOnceTask
        exit $EXIT_OK
    }

    $runStart = Get-Date
    Write-RestoreLog 'STEP' "gdrive-restore set=$SetStamp mode=$(if ($AutoRestore) { "auto-restore -> $TargetDb" } else { 'download only' }) unattended=$([bool]$Unattended)"

    # gpg is required in every download path (envelope verification).
    $Gpg = Resolve-GpgPath
    if (-not $Gpg) {
        Exit-RestoreFail -Code $EXIT_VERIFY_FAILED `
            -Message 'gpg.exe not found (PATH or Gpg4win default location) - cannot verify or decrypt backup artifacts. Install Gpg4win: winget install GnuPG.Gpg4win' `
            -AuditFile "set-$SetStamp"
    }

    # Resolve the passphrase EARLY for -AutoRestore (TOC gate decrypts the
    # dump; restore-native decrypts again in its own process). Unattended
    # runs must find it in .env - there is no console to prompt on.
    $pp = $null
    if ($AutoRestore) {
        $pp = $Passphrase
        if (-not $pp -and (Test-Path $EnvPath)) {
            $line = Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1
            if ($line) {
                $envPass = $line.Matches.Groups[1].Value.Trim()
                if ($envPass) { $pp = ConvertTo-SecureString $envPass -AsPlainText -Force }
                $envPass = $null
            }
        }
        if (-not $pp) {
            if ($Unattended) {
                Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
                    -Message 'Unattended mode requires BACKUP_PASSPHRASE in .env (no interactive prompt available). Restore aborted before touching anything.' `
                    -AuditFile "set-$SetStamp"
            }
            $pp = Read-Host 'Enter BACKUP_PASSPHRASE' -AsSecureString
        }
    }

    # --- Step 1 (auto only): emergency pre-restore backup ------------------
    # Targets the deployment's primary db (-CatalogDb, prod 'wms' by default)
    # so the box always holds a fresh snapshot before anything is overwritten.
    if ($AutoRestore) {
        Write-RestoreLog 'STEP' "Step 1/7: emergency pre-restore backup of '$($script:Conn.DbName)' (backup-native.ps1 -Source emergency)..."
        if (-not (Test-Path $BackupNative)) {
            Exit-RestoreFail -Code $EXIT_RESTORE_FAILED -Message "backup-native.ps1 not found at $BackupNative - cannot take the emergency backup; restore aborted." -AuditFile "set-$SetStamp"
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $BackupNative -Source emergency -FilePrefix 'emergency-' `
            -DbName $script:Conn.DbName -DbHost $script:Conn.DbHost -DbPort $script:Conn.DbPort -DbUser $script:Conn.DbUser
        if ($LASTEXITCODE -ne 0) {
            Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
                -Message "Emergency pre-restore backup FAILED (exit $LASTEXITCODE). Restore aborted - nothing touched. Fix the backup pipeline first." `
                -AuditFile "set-$SetStamp"
        }
        Write-RestoreLog 'OK' 'Emergency backup complete (emergency-*.dump.gpg, retention-exempt).'
    }

    # --- Step 2: download + triple verification -----------------------------
    Write-RestoreLog 'STEP' "Step 2/7: download + verify set $SetStamp -> $DownloadTo"
    $dl = Invoke-GDriveSetDownload -Stamp $SetStamp -Staging $DownloadTo -GpgExe $Gpg

    if (-not $AutoRestore) {
        # Download-only: audit + print the exact next command, then stop.
        Write-RestoreAudit -Success $true -FileName $dl.DbLeaf -SizeMb $dl.SizeMb `
            -TocEntries $dl.TocEntries -Verified $true -Checksum $dl.DbSha `
            -DurationSeconds ((Get-Date) - $runStart).TotalSeconds `
            -Message "Drive set $SetStamp downloaded + verified to $DownloadTo (download only, no restore)"
        Write-RestoreEvent -EventId 400 -EntryType Information `
            -Message "gdrive-restore: set $SetStamp downloaded + verified to $DownloadTo (download only)."
        $suggestDb = $TargetDb
        if (-not $suggestDb) { $suggestDb = 'wms_restore_' + ($SetStamp -replace '-', '_') }
        Write-RestoreLog 'OK' "Set $SetStamp downloaded + verified. Nothing was restored."
        Write-Host ''
        Write-Host 'Next step - restore it manually:' -ForegroundColor Cyan
        Write-Host ('    scripts\restore-native.ps1 -BackupFile "{0}" -DbName {1} -Force' -f $dl.DbPath, $suggestDb) -ForegroundColor Yellow
        Write-Host 'or let this script orchestrate everything (emergency backup, service stop/start, probes):' -ForegroundColor Cyan
        Write-Host ('    scripts\gdrive-restore.ps1 -SetStamp {0} -AutoRestore -TargetDb {1}' -f $SetStamp, $suggestDb) -ForegroundColor Yellow
        exit $EXIT_OK
    }

    # --- Step 3: pg_restore --list TOC gate on the decrypted dump -----------
    Write-RestoreLog 'STEP' 'Step 3/7: pg_restore --list TOC gate (>= 100 entries) on the downloaded dump...'
    $tmpDump = [System.IO.Path]::GetTempFileName() + '.dump'
    $tocLines = 0
    try {
        Start-GpgDecrypt -Pass $pp -InputFile $dl.DbPath -OutputFile $tmpDump -GpgExe $Gpg
        $tocFile = [System.IO.Path]::GetTempFileName()
        $tocErr  = [System.IO.Path]::GetTempFileName()
        try {
            $cmd = 'pg_restore --list "' + $tmpDump + '" > "' + $tocFile + '" 2> "' + $tocErr + '"'
            & cmd /c $cmd
            if ($LASTEXITCODE -ne 0) {
                $errTxt = Get-Content $tocErr -Raw -ErrorAction SilentlyContinue
                throw "pg_restore --list rejected the dump (exit $LASTEXITCODE): $errTxt"
            }
            $tocLines = @(Get-Content -LiteralPath $tocFile -ErrorAction SilentlyContinue).Count
        } finally {
            Remove-Item -LiteralPath $tocFile, $tocErr -Force -ErrorAction SilentlyContinue
        }
        if ($tocLines -lt 100) {
            throw "dump has only $tocLines TOC entries - expected 100+ (truncated or wrong artifact)"
        }
    } catch {
        Exit-RestoreFail -Code $EXIT_VERIFY_FAILED -Message "TOC gate failed for set ${SetStamp}: $($_.Exception.Message)" -AuditFile $dl.DbLeaf
    } finally {
        Remove-Item -LiteralPath $tmpDump -Force -ErrorAction SilentlyContinue
    }
    Write-RestoreLog 'OK' "TOC gate passed ($tocLines entries)."

    # --- Step 4: stop the service (only when the live install is at risk) ---
    # restore-native extracts the set's filestore into the LIVE data_dir under
    # the SOURCE db's folder name, so the service must stop when the target is
    # the production db OR the set is a backup OF the production db (or its
    # source db is unrecorded - assume the worst). A scratch set restored into
    # a scratch target cannot collide with the live filestore, so drills leave
    # production running (spec 12(d).3 runs against scratch DBs only).
    $HttpPort = 8069
    if (Test-Path $ConfPath) {
        $m = Select-String -Path $ConfPath -Pattern '^http_port\s*=\s*(\d+)$' | Select-Object -First 1
        if (-not $m) { $m = Select-String -Path $ConfPath -Pattern '^xmlrpc_port\s*=\s*(\d+)$' | Select-Object -First 1 }
        if ($m) { $HttpPort = [int]$m.Matches.Groups[1].Value }
    }
    $svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
    $svcStopped = $false
    $setDbName = [string]$dl.DbName
    $needsStop = ($TargetDb -ieq $ProdDbName) -or (-not $setDbName) -or ($setDbName -ieq $ProdDbName)
    if ($svc -and $needsStop) {
        Write-RestoreLog 'STEP' "Step 4/7: stopping service '$ServiceName' (port $HttpPort)..."
        if ($svc.Status -ne 'Stopped') {
            try {
                Stop-Service $ServiceName -Force
            } catch {
                Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
                    -Message "Could not stop service '$ServiceName' (Administrator rights required): $($_.Exception.Message). Restore aborted BEFORE touching the target database." `
                    -AuditFile $dl.DbLeaf
            }
            for ($i = 0; $i -lt 20 -and (Get-NetTCPConnection -LocalPort $HttpPort -State Listen -ErrorAction SilentlyContinue); $i++) {
                Start-Sleep -Seconds 1
            }
        }
        $svcStopped = $true
        Write-RestoreLog 'OK' 'Service stopped; HTTP port is free.'
    } elseif ($svc) {
        Write-RestoreLog 'STEP' "Step 4/7: service '$ServiceName' left RUNNING - neither target '$TargetDb' nor the set's source db '$setDbName' is the live '$ProdDbName' database (no filestore collision)."
    } else {
        Write-RestoreLog 'WARN' "Service '$ServiceName' is not installed - continuing without a service stop/start."
    }

    # --- Step 5: restore-native ----------------------------------------------
    Write-RestoreLog 'STEP' "Step 5/7: restore-native.ps1 -BackupFile $($dl.DbLeaf) -DbName $TargetDb -Force"
    if (-not (Test-Path $RestoreNative)) {
        Exit-RestoreFail -Code $EXIT_RESTORE_FAILED -Message "restore-native.ps1 not found at $RestoreNative." -AuditFile $dl.DbLeaf
    }
    # Child process: restore-native uses bare `exit` on errors, which would
    # kill this orchestrator if dot-invoked. It re-reads the passphrase from
    # .env itself (or prompts on an attended console).
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RestoreNative `
        -BackupFile $dl.DbPath -DbName $TargetDb -Force `
        -DbHost $script:Conn.DbHost -DbPort $script:Conn.DbPort -DbUser $script:Conn.DbUser
    if ($LASTEXITCODE -ne 0) {
        Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
            -Message "restore-native.ps1 FAILED (exit $LASTEXITCODE) restoring set $SetStamp into '$TargetDb'. Service left STOPPED. Roll back with the emergency-*.dump.gpg backup if needed." `
            -AuditFile $dl.DbLeaf
    }

    # --- Step 6: integrity probes -------------------------------------------
    Write-RestoreLog 'STEP' "Step 6/7: integrity probes on '$TargetDb' (res_users, ir_module_module)..."
    $usersCount = -1
    $modulesCount = -1
    try {
        $out = & psql -U $script:Conn.DbUser -h $script:Conn.DbHost -p $script:Conn.DbPort -d $TargetDb -w -t -A `
            -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM res_users;' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $v = @($out) | Where-Object { "$_" -match '^\s*\d+\s*$' } | Select-Object -First 1
            if ($null -ne $v) { $usersCount = [int]("$v".Trim()) }
        }
        $out = & psql -U $script:Conn.DbUser -h $script:Conn.DbHost -p $script:Conn.DbPort -d $TargetDb -w -t -A `
            -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM ir_module_module;' 2>$null
        if ($LASTEXITCODE -eq 0) {
            $v = @($out) | Where-Object { "$_" -match '^\s*\d+\s*$' } | Select-Object -First 1
            if ($null -ne $v) { $modulesCount = [int]("$v".Trim()) }
        }
    } catch { }
    if ($usersCount -lt 1 -or $modulesCount -lt 1) {
        Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
            -Message "Post-restore integrity probes FAILED on '$TargetDb' (res_users=$usersCount, ir_module_module=$modulesCount). The restored database looks unusable; service left STOPPED. Emergency backup is available for rollback." `
            -AuditFile $dl.DbLeaf
    }
    Write-RestoreLog 'OK' "Probes passed: res_users=$usersCount, ir_module_module=$modulesCount."

    # --- Step 7: restart service + health poll + bookkeeping -----------------
    $svcNote = '; service not installed (no stop/start)'
    if ($svc -and -not $svcStopped) { $svcNote = '; service left running (scratch target, no live-db collision)' }
    if ($svcStopped) {
        Write-RestoreLog 'STEP' "Step 7/7: starting '$ServiceName' + polling /wms/health (max 180 s)..."
        Start-Service $ServiceName
        $healthy = $false
        for ($i = 1; $i -le 36; $i++) {
            try {
                $resp = Invoke-WebRequest "http://localhost:$HttpPort/wms/health" -UseBasicParsing -TimeoutSec 5
                if ($resp.StatusCode -eq 200) {
                    $status = ($resp.Content | ConvertFrom-Json).status
                    Write-RestoreLog 'OK' "Service healthy after ~$($i * 5)s : $status"
                    $healthy = $true
                    break
                }
            } catch { }
            Start-Sleep -Seconds 5
        }
        if (-not $healthy) {
            Exit-RestoreFail -Code $EXIT_RESTORE_FAILED `
                -Message "Set $SetStamp restored into '$TargetDb' and the service was started, but /wms/health did not confirm within 180 s. Check .runtime\logs\service-err.log before trusting this restore." `
                -AuditFile $dl.DbLeaf
        }
        $svcNote = '; service restarted + health confirmed'
    }

    $duration = ((Get-Date) - $runStart).TotalSeconds
    Write-RestoreAudit -Success $true -FileName $dl.DbLeaf -SizeMb $dl.SizeMb `
        -TocEntries $tocLines -Verified $true -Checksum $dl.DbSha -DurationSeconds $duration `
        -Message "Drive set $SetStamp restored into '$TargetDb' (res_users=$usersCount, modules=$modulesCount, toc=$tocLines)$svcNote"
    Update-RestoredCount -Stamp $SetStamp
    Send-Heartbeat -Url $script:HeartbeatUrl
    Write-RestoreEvent -EventId 400 -EntryType Information `
        -Message "gdrive-restore: set $SetStamp restored into '$TargetDb' (res_users=$usersCount, modules=$modulesCount)$svcNote."
    Write-RestoreLog 'OK' "Restore of set $SetStamp into '$TargetDb' complete ($([math]::Round($duration, 1)) s)$svcNote."
    exit $EXIT_OK
} finally {
    # One-shot task hygiene: the unattended run removes 'WMS Restore Once'
    # whatever the outcome, so a failed restore cannot re-fire at boot.
    if ($Unattended) {
        try {
            if (Get-ScheduledTask -TaskName $OnceTaskName -ErrorAction SilentlyContinue) {
                Unregister-ScheduledTask -TaskName $OnceTaskName -Confirm:$false
                Write-RestoreLog 'INFO' "One-shot task '$OnceTaskName' unregistered."
            }
        } catch {
            Write-RestoreLog 'WARN' "Could not unregister '$OnceTaskName' (ignored): $($_.Exception.Message)"
        }
    }
}

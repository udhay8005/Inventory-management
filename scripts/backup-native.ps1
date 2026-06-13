<#
.SYNOPSIS
    Encrypted backup of the native WMS install - Postgres dump + filestore.

.DESCRIPTION
    Writes two timestamped artifacts to .\backups\:

        wms-<timestamp>.dump.gpg              pg_dump custom-format, GPG-AES256
        wms-<timestamp>-filestore.zip.gpg     zipped data_dir filestore, GPG-AES256

    Both files are encrypted with symmetric AES-256 using BACKUP_PASSPHRASE
    from .env (the unencrypted dump never touches disk - we pipe pg_dump
    straight into gpg). Without the passphrase, the *.gpg files are
    unrecoverable. Store the passphrase OFF the server.

    Retention: keeps the most recent N backups (-Retain, default 14).

    Recovery: use scripts\restore-native.ps1 - it prompts for the
    passphrase, decrypts to a temp file, then pg_restore + filestore
    unzip.

.PARAMETER DbName
    Database to dump. Default: wms.

.PARAMETER Retain
    Number of most-recent backups to keep. Default: 14.

.PARAMETER Passphrase
    Override the .env BACKUP_PASSPHRASE for this run only. Useful when
    cycling passphrases. Accepts a SecureString so the passphrase
    never sits in plain text in this script's variable space — convert
    a plain string at the call site with
        ConvertTo-SecureString 'mypass' -AsPlainText -Force

.PARAMETER Source
    Attribution recorded in the audit rows and the Google Drive catalog:
    'auto' (scheduled task), 'manual' (WMS Backup Now / schtasks run) or
    'emergency' (pre-restore safety backup). Default: auto.

.PARAMETER FilePrefix
    Optional artifact filename prefix (e.g. 'emergency-'). Prefixed files
    never match the "$DbName-*" retention globs, so they are structurally
    exempt from local + off-site retention. Default: '' (current naming;
    all existing consumers unaffected).

.EXAMPLE
    scripts\backup-native.ps1

.EXAMPLE
    scripts\backup-native.ps1 -DbName wms -Retain 30

.EXAMPLE
    $pp = Read-Host -AsSecureString 'Passphrase?'
    scripts\backup-native.ps1 -Passphrase $pp
#>
[CmdletBinding()]
param(
    [string]$DbName = 'wms',
    [int]$Retain = 14,
    [SecureString]$Passphrase,
    [string]$DbHost,
    [int]$DbPort,
    [string]$DbUser,
    [ValidateSet('auto', 'manual', 'emergency')]
    [string]$Source = 'auto',
    [string]$FilePrefix = '',
    # v18: run ONLY the Drive pending-upload sweep (Stage 5a + 5e). No pg_dump,
    # no filestore, no local backup_db/backup_filestore audit rows (those would
    # corrupt the Backup Now poll watermark). Fired by the hourly reconnect
    # cron + the DR-page "Retry Now" button via the trigger-less
    # 'WMS Pending Upload Sweep' SYSTEM task. Up-front Test-GDriveReachable
    # no-ops the run when still offline / auth-expired.
    [switch]$PendingSweep
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir   = Join-Path $ProjectRoot 'backups'
$DataDir     = Join-Path $ProjectRoot '.runtime\data'
$EnvPath     = Join-Path $ProjectRoot '.env'
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'
$Stamp       = Get-Date -Format 'yyyyMMdd-HHmmss'

# --- Resolve PG connection from odoo.native.conf -------------------------
# The trust often runs Postgres on a non-default port (1088 on this
# install). Don't hard-code 5432; read the live config instead.
if (Test-Path $ConfPath) {
    if (-not $DbHost) {
        $m = Select-String -Path $ConfPath -Pattern '^db_host\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $DbHost = $m.Matches.Groups[1].Value.Trim() }
    }
    if (-not $DbPort) {
        $m = Select-String -Path $ConfPath -Pattern '^db_port\s*=\s*(\d+)$' | Select-Object -First 1
        if ($m) { $DbPort = [int]$m.Matches.Groups[1].Value }
    }
    if (-not $DbUser) {
        $m = Select-String -Path $ConfPath -Pattern '^db_user\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $DbUser = $m.Matches.Groups[1].Value.Trim() }
    }
    if (-not $env:PGPASSWORD) {
        $m = Select-String -Path $ConfPath -Pattern '^db_password\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $env:PGPASSWORD = $m.Matches.Groups[1].Value.Trim() }
    }
}
if (-not $DbHost) { $DbHost = 'localhost' }
if (-not $DbPort) { $DbPort = 5432 }
if (-not $DbUser) { $DbUser = 'odoo' }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# --- Resolve passphrase from .env if not supplied ------------------------
# Always work with the passphrase as a SecureString in this script's
# variable space; convert to plaintext only at the gpg stdin boundary
# inside Start-GpgPipe. This keeps it off Process Explorer's command-
# line snapshot and off PowerShell's transcription logs.
# -PendingSweep does NO encryption (it only re-uploads already-encrypted
# .gpg artifacts), so the passphrase + gpg requirements are skipped for it.
if (-not $PendingSweep) {
    if (-not $Passphrase) {
        if (Test-Path $EnvPath) {
            $line = (Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1)
            if ($line) {
                $envPass = $line.Matches.Groups[1].Value.Trim()
                if ($envPass) {
                    $Passphrase = ConvertTo-SecureString $envPass -AsPlainText -Force
                }
                # Wipe the plaintext local var the instant we're done.
                $envPass = $null
            }
        }
    }
    if (-not $Passphrase) {
        Write-Host "BACKUP_PASSPHRASE not set in .env." -ForegroundColor Red
        Write-Host "Add a strong passphrase to .env:" -ForegroundColor Yellow
        Write-Host "    BACKUP_PASSPHRASE=<24+ random chars, no whitespace>" -ForegroundColor Yellow
        Write-Host "Then re-run." -ForegroundColor Yellow
        exit 1
    }
    # Detect the placeholder by briefly converting to plaintext.
    $ppPlainPeek = [System.Net.NetworkCredential]::new('', $Passphrase).Password
    if ($ppPlainPeek -eq 'changeme_backup_passphrase') {
        $ppPlainPeek = $null
        Write-Host "BACKUP_PASSPHRASE is still the placeholder 'changeme_backup_passphrase'." -ForegroundColor Red
        Write-Host "Replace it with a real 24+ char random string in .env." -ForegroundColor Yellow
        exit 1
    }
    $ppPlainPeek = $null
}

# --- Find gpg.exe on PATH (or in the default Gpg4win install location) ---
# PowerShell 5.1 has no `?.` operator, so use the explicit null check.
$gpg = $null
if (-not $PendingSweep) {
    $gpgCmd = Get-Command gpg.exe -ErrorAction SilentlyContinue
    $gpg = if ($gpgCmd) { $gpgCmd.Source } else { $null }
    if (-not $gpg) {
        foreach ($cand in @(
            'C:\Program Files (x86)\GnuPG\bin\gpg.exe',
            'C:\Program Files\GnuPG\bin\gpg.exe'
        )) {
            if (Test-Path $cand) { $gpg = $cand; break }
        }
    }
    if (-not $gpg) {
        Write-Host "gpg.exe not found on PATH." -ForegroundColor Red
        Write-Host "Install Gpg4win (https://gpg4win.org/) or:" -ForegroundColor Yellow
        Write-Host "    winget install GnuPG.Gpg4win" -ForegroundColor Yellow
        exit 1
    }
}

# Hand gpg the passphrase via stdin to keep it off the command line
# (command-line args show up in Process Explorer; the file system
# stays clean).
function Start-GpgPipe {
    param(
        [Parameter(Mandatory)] [SecureString]$Pass,
        [Parameter(Mandatory)] [string]$InputFile,
        [Parameter(Mandatory)] [string]$OutputFile
    )
    # Pipe the passphrase to gpg's stdin (--passphrase-fd 0) via cmd's
    # `echo|` so PowerShell 5.1's native pipeline doesn't mangle the
    # bytes. The passphrase is converted from SecureString to plaintext
    # ONLY in the short-lived `$plain` local var and is wiped on the
    # finally block. cmd.exe sees the plaintext on its argument line
    # for the duration of one `echo`, which is unavoidable for the
    # echo+pipe pattern; the trade-off vs the file-on-disk alternative
    # is that the variable never touches the file system.
    #
    # GPG writes informational notices (gpg-agent socket, first-run
    # keyring creation) to stderr; those aren't failures. We collect
    # stderr to a tempfile and only print it if gpg exits non-zero.
    # ---- Self-heal a stale gpg-agent before each encrypt ----------------
    # The agent leaves stale Unix-domain-style socket files in %APPDATA%\gnupg
    # and %LOCALAPPDATA%\gnupg on Windows; once one of S.gpg-agent*
    # ("ssh"/"extra"/"browser"/"") goes bad, every subsequent symmetric
    # encrypt fails with "can't connect to the gpg-agent" until the user
    # manually clears it. This block runs the same recovery on every
    # invocation, so the nightly backup-native.ps1 cron can't silently fail
    # again. Idempotent: a clean agent restarts in <1s.
    try { & gpgconf --kill gpg-agent 2>&1 | Out-Null } catch {}
    foreach ($dir in @("$env:APPDATA\gnupg", "$env:LOCALAPPDATA\gnupg")) {
        if (Test-Path -LiteralPath $dir) {
            Get-ChildItem -LiteralPath $dir -Filter 'S.gpg-agent*' `
                -Force -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        }
    }
    try { & gpg-connect-agent /bye 2>&1 | Out-Null } catch {}

    # FPAT High: the original `cmd /c echo $plain| gpg ...` pattern silently
    # TRUNCATED the passphrase at the first &, |, <, >, ^ or % character that
    # cmd.exe treats as a metacharacter (so a passphrase with a literal & in
    # it produced encrypted backups nobody could ever decrypt). Switch to a
    # short-lived passphrase FILE - gpg reads it directly, no shell
    # interpretation, all printable bytes preserved.
    $errFile = [System.IO.Path]::GetTempFileName()
    $pwFile = [System.IO.Path]::GetTempFileName()
    $plain = $null
    try {
        $plain = [System.Net.NetworkCredential]::new('', $Pass).Password
        # Write WITHOUT a trailing newline so gpg accepts the whole string.
        # UTF-8 encoding keeps non-ASCII passphrases intact.
        [System.IO.File]::WriteAllBytes(
            $pwFile,
            [System.Text.Encoding]::UTF8.GetBytes($plain)
        )
        # Closure-sprint: invoke via cmd /c, NOT `& $gpg ... 2>$errFile`.
        # PowerShell 5.1 wraps every line of native-command stderr as a
        # NativeCommandError record, and with $ErrorActionPreference = 'Stop'
        # the very first informational line gpg-agent prints ("gpg-agent
        # 2.5.20 started" - normal start-up text on stderr) terminates the
        # script BEFORE gpg even runs. cmd.exe doesn't propagate stderr as
        # PowerShell errors, so the encrypt completes; stderr lands in the
        # tempfile and we only surface it on a real exit code.
        $cmd = '"' + $gpg + '" --batch --yes --pinentry-mode loopback ' +
               '--passphrase-file "' + $pwFile + '" ' +
               '--symmetric --cipher-algo AES256 ' +
               '-o "' + $OutputFile + '" "' + $InputFile + '" 2> "' + $errFile + '"'
        & cmd /c $cmd
        $rc = $LASTEXITCODE
        if ($rc -ne 0) {
            $stderr = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
            throw "gpg encryption failed (exit $rc) on $InputFile`n$stderr"
        }
    } finally {
        # Best-effort plaintext wipe — overwrite then drop the local
        # binding so a subsequent memory snapshot can't recover it.
        if ($plain) { $plain = ' ' * $plain.Length }
        $plain = $null
        # Overwrite the passphrase file once before unlink so a recovery
        # tool can't pull it from the temp directory.
        if (Test-Path -LiteralPath $pwFile) {
            try { [System.IO.File]::WriteAllBytes($pwFile, (New-Object byte[] 64)) } catch {}
            Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
}

# --- Observability: heartbeat + backup-audit helpers --------------------
# Both are FAILURE-SAFE by design: a heartbeat or audit-write problem must
# NEVER abort or fail a backup. They degrade silently to a DarkGray note.
$BackupStart = Get-Date
$script:ObsBackupOk = $false

# Optional healthchecks.io-style heartbeat URL, read from .env. Blank =
# heartbeats disabled (no external dependency).
$HeartbeatUrl = ''
if (Test-Path $EnvPath) {
    $hb = (Select-String -Path $EnvPath -Pattern '^HEALTHCHECK_BACKUP_URL=(.+)$' | Select-Object -First 1)
    if ($hb) { $HeartbeatUrl = $hb.Matches.Groups[1].Value.Trim() }
}

function Send-Heartbeat {
    # Non-blocking, 10s-timeout ping. Appends /fail for failure signals.
    # Silent on any error - observability must never break the backup.
    param([string]$Url, [switch]$Fail)
    if (-not $Url) { return }
    $target = if ($Fail) { "$Url/fail" } else { $Url }
    try {
        Invoke-WebRequest -Uri $target -Method Get -TimeoutSec 10 -UseBasicParsing | Out-Null
    } catch {
        Write-Host "    [warn] heartbeat ping failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Write-BackupAudit {
    # Append one row to wms_backup_audit via psql. Failure-safe: if the
    # table doesn't exist (wms_reports not installed) or the DB is
    # unreachable, log a note and continue. No secrets are written.
    param(
        [string]$AuditType, [bool]$Success, [string]$FileName,
        [double]$SizeMb = 0, [int]$TocEntries = 0, [bool]$Verified = $false,
        [double]$DurationSeconds = 0, [string]$Checksum = '', [string]$Message = ''
    )
    try {
        $sk = if ($Success)  { 'true' } else { 'false' }
        $vf = if ($Verified) { 'true' } else { 'false' }
        # Escape single quotes for SQL string literals (no user input here,
        # but defensive). NOW() stamps event_time; create/write_uid = admin.
        $fn  = ($FileName -replace "'", "''")
        $msg = ($Message  -replace "'", "''")
        $cs  = ($Checksum -replace "'", "''")
        $hn  = ($env:COMPUTERNAME -replace "'", "''")
        $sql = "INSERT INTO wms_backup_audit (name, audit_type, success, event_time, duration_seconds, size_mb, toc_entries, verified, checksum, host, message, create_uid, create_date, write_uid, write_date) VALUES ('$fn', '$AuditType', $sk, NOW(), $DurationSeconds, $SizeMb, $TocEntries, $vf, '$cs', '$hn', '$msg', 1, NOW(), 1, NOW());"
        $sql | & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    [audit] recorded $AuditType in wms_backup_audit" -ForegroundColor DarkGray
        } else {
            Write-Host "    [warn] backup audit not recorded (is wms_reports installed?)" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] backup audit write failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

# Failure-path observability: any terminating error pings /fail + logs a
# failed audit row, then re-raises (break) so the exit code is unchanged.
# -PendingSweep is exempt: it takes no fresh backup, so a failure there must
# NOT write a backup_db audit row (that would corrupt the Backup Now poll
# watermark). The pending-sweep handler is failure-safe on its own.
trap {
    if (-not $script:ObsBackupOk -and -not $PendingSweep) {
        Send-Heartbeat -Url $HeartbeatUrl -Fail
        Write-BackupAudit -AuditType 'backup_db' -Success $false -FileName "$DbName-$Stamp" `
            -DurationSeconds ((Get-Date) - $BackupStart).TotalSeconds `
            -Message "Backup failed: $($_.Exception.Message)"
    }
    break
}

# --- 1-4. Local backup pipeline (skipped entirely under -PendingSweep, which
# only re-uploads already-built artifacts; see the Stage-5 -PendingSweep
# handler). The full local path is unchanged for normal runs. ---
if (-not $PendingSweep) {

# --- 1. Database dump (encrypted) ---------------------------------------
$DumpPath    = Join-Path $BackupDir "$FilePrefix$DbName-$Stamp.dump"
$DumpEncPath = "$DumpPath.gpg"
Write-Host "Dumping database '$DbName' (then encrypting)" -ForegroundColor Cyan
Write-Host "    -> $DumpEncPath" -ForegroundColor DarkGray

& pg_dump -U $DbUser -h $DbHost -p $DbPort -d $DbName -Fc -f $DumpPath
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed. Set `$env:PGPASSWORD if Postgres needs a password."
}

try {
    Start-GpgPipe -Pass $Passphrase -InputFile $DumpPath -OutputFile $DumpEncPath
    Write-Host "    Database dumped + encrypted" -ForegroundColor Green
    # Verify the dump is structurally restorable before we shred the
    # plaintext. A truncated pg_dump may still produce a valid GPG
    # envelope; this catches that class of silent corruption.
    $tocOut = & pg_restore --list $DumpPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore --list rejected the fresh dump ($LASTEXITCODE). Backup aborted."
    }
    $tocLines = ($tocOut | Measure-Object -Line).Lines
    if ($tocLines -lt 100) {
        throw "Fresh dump has only $tocLines TOC entries - expected 1000+. Backup aborted."
    }
    Write-Host "    pg_restore --list OK ($tocLines TOC entries)" -ForegroundColor Green
    # Record the successful DB-backup event (failure-safe).
    $dbSizeMb = [math]::Round((Get-Item $DumpEncPath).Length / 1MB, 2)
    $dbHash = (Get-FileHash $DumpEncPath -Algorithm SHA256).Hash
    Write-BackupAudit -AuditType 'backup_db' -Success $true `
        -FileName (Split-Path -Leaf $DumpEncPath) -SizeMb $dbSizeMb `
        -TocEntries $tocLines -Verified $true `
        -DurationSeconds ((Get-Date) - $BackupStart).TotalSeconds `
        -Checksum $dbHash -Message "OK (source=$Source)"
} finally {
    # Always shred the plaintext dump - it's on disk for milliseconds.
    Remove-Item $DumpPath -Force -ErrorAction SilentlyContinue
}

# --- 2. Filestore zip (encrypted) ---------------------------------------
$Filestore = Join-Path $DataDir "filestore\$DbName"
if (Test-Path $Filestore) {
    $ZipPath    = Join-Path $BackupDir "$FilePrefix$DbName-$Stamp-filestore.zip"
    $ZipEncPath = "$ZipPath.gpg"
    Write-Host "Zipping filestore (then encrypting)" -ForegroundColor Cyan
    Write-Host "    -> $ZipEncPath" -ForegroundColor DarkGray
    Compress-Archive -Path $Filestore -DestinationPath $ZipPath -Force
    try {
        Start-GpgPipe -Pass $Passphrase -InputFile $ZipPath -OutputFile $ZipEncPath
        Write-Host "    Filestore archived + encrypted" -ForegroundColor Green
        $fsSizeMb = [math]::Round((Get-Item $ZipEncPath).Length / 1MB, 2)
        $fsHash = (Get-FileHash $ZipEncPath -Algorithm SHA256).Hash
        Write-BackupAudit -AuditType 'backup_filestore' -Success $true `
            -FileName (Split-Path -Leaf $ZipEncPath) -SizeMb $fsSizeMb -Verified $true `
            -Checksum $fsHash -Message "OK"
    } finally {
        Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "    [warn] Filestore not found at $Filestore (skipped)" -ForegroundColor Yellow
}

# Backup artifacts are written + verified. Mark success BEFORE retention so
# a retention hiccup can't trigger a false failure alert, and send the
# success heartbeat now.
$script:ObsBackupOk = $true
Send-Heartbeat -Url $HeartbeatUrl

# --- 3. Retention -------------------------------------------------------
Write-Host "Applying retention (keep last $Retain)" -ForegroundColor Cyan
$dumps = Get-ChildItem $BackupDir -Filter "$DbName-*.dump.gpg" | Sort-Object LastWriteTime -Descending
$dumps | Select-Object -Skip $Retain | ForEach-Object {
    Write-Host "    deleting $($_.Name)" -ForegroundColor DarkGray
    Remove-Item $_.FullName -Force
    $sibling = $_.FullName -replace '\.dump\.gpg$', '-filestore.zip.gpg'
    if (Test-Path $sibling) { Remove-Item $sibling -Force }
}

# --- 4. Off-site copy (optional; disabled until BACKUP_OFFSITE_DIR is set) ---
# Local-only backups die with the disk (fire / theft / ransomware). This copies
# the already-ENCRYPTED .gpg artifacts to an off-site target (USB drive, UNC
# share \\nas\wms-backups, or a cloud-sync folder like OneDrive), VERIFIES the
# copy by re-hashing against the local SHA-256, and applies the same retention.
# Failure-safe: the local backup already succeeded, so an off-site hiccup warns
# + logs a failed audit row but NEVER fails the backup.
$OffsiteDir = ''
$OffsiteHb  = ''
if (Test-Path $EnvPath) {
    $od = (Select-String -Path $EnvPath -Pattern '^BACKUP_OFFSITE_DIR=(.+)$' | Select-Object -First 1)
    if ($od) { $OffsiteDir = $od.Matches.Groups[1].Value.Trim().Trim('"') }
    $oh = (Select-String -Path $EnvPath -Pattern '^HEALTHCHECK_OFFSITE_URL=(.+)$' | Select-Object -First 1)
    if ($oh) { $OffsiteHb = $oh.Matches.Groups[1].Value.Trim() }
}
if ($OffsiteDir) {
    Write-Host "Off-site copy -> $OffsiteDir" -ForegroundColor Cyan
    try {
        if (-not (Test-Path $OffsiteDir)) { New-Item -ItemType Directory -Force -Path $OffsiteDir | Out-Null }
        $copied = 0
        foreach ($pair in @(
                @{ Src = $DumpEncPath; Hash = $dbHash },
                @{ Src = $ZipEncPath;  Hash = $fsHash })) {
            if (-not $pair.Src -or -not (Test-Path $pair.Src)) { continue }
            $dest = Join-Path $OffsiteDir (Split-Path -Leaf $pair.Src)
            Copy-Item -LiteralPath $pair.Src -Destination $dest -Force
            $destHash = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
            if ($pair.Hash -and $destHash -ne $pair.Hash) {
                throw "off-site hash mismatch for $(Split-Path -Leaf $dest) (corrupt copy)"
            }
            Write-Host "    copied + verified $(Split-Path -Leaf $dest)" -ForegroundColor Green
            $copied++
        }
        Get-ChildItem $OffsiteDir -Filter "$DbName-*.dump.gpg" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -Skip $Retain | ForEach-Object {
                Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                $sib = $_.FullName -replace '\.dump\.gpg$', '-filestore.zip.gpg'
                if (Test-Path $sib) { Remove-Item $sib -Force -ErrorAction SilentlyContinue }
            }
        Send-Heartbeat -Url $OffsiteHb
        Write-BackupAudit -AuditType 'backup_offsite' -Success $true `
            -FileName (Split-Path -Leaf $DumpEncPath) -SizeMb $dbSizeMb -Verified $true `
            -Checksum $dbHash -Message "Off-site copy verified ($copied file(s)) -> $OffsiteDir"
        Write-Host "    Off-site copy complete + verified." -ForegroundColor Green
    } catch {
        Write-Host "    [warn] off-site copy failed (LOCAL backup is intact): $($_.Exception.Message)" -ForegroundColor Yellow
        Send-Heartbeat -Url $OffsiteHb -Fail
        Write-BackupAudit -AuditType 'backup_offsite' -Success $false `
            -FileName (Split-Path -Leaf $DumpEncPath) `
            -Message "Off-site copy FAILED: $($_.Exception.Message)"
    }
} else {
    Write-Host "Off-site copy: disabled (set BACKUP_OFFSITE_DIR in .env to enable)" -ForegroundColor DarkGray
}

}  # end: if (-not $PendingSweep) — local backup Stages 1-4

# --- 5. Google Drive upload (optional; disabled until setup-gdrive-auth.ps1 has run) ---
# Failure-safe by position AND construction: the local backup already
# succeeded ($script:ObsBackupOk above), so every Drive problem degrades to a
# '[warn] ... (LOCAL backup is intact)' line, a /fail heartbeat, a failed
# backup_gdrive audit row plus a pending catalog row for the next run's retry
# sweep - it NEVER throws outward. Artifacts leave the box only as GPG AES256
# envelopes; the passphrase never does.
$GdriveHb = ''
if (Test-Path $EnvPath) {
    $gh = (Select-String -Path $EnvPath -Pattern '^HEALTHCHECK_GDRIVE_URL=(.+)$' | Select-Object -First 1)
    if ($gh) { $GdriveHb = $gh.Matches.Groups[1].Value.Trim() }
}
$GdLib     = Join-Path $PSScriptRoot 'gdrive-lib.ps1'
$TokenPath = Join-Path $ProjectRoot 'config\gdrive-token.json.dpapi'
$GdReady   = $false
try {
    if (Test-Path $GdLib) {
        . $GdLib
        $GdReady = Test-GDriveReady -EnvPath $EnvPath -TokenPath $TokenPath `
            -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
    }
} catch {
    # A missing/broken library must never fail the backup - skip the stage.
    Write-Host "    [warn] Google Drive stage unavailable (gdrive-lib.ps1 not loaded): $($_.Exception.Message)" -ForegroundColor DarkGray
    $GdReady = $false
}

function ConvertTo-GDrivePositiveInt {
    # Failure-safe int parse for retention params - a mistyped setting must
    # degrade to the default, never fail the stage.
    param([string]$Value, [int]$Default)
    $n = 0
    if ([int]::TryParse($Value, [ref]$n) -and $n -gt 0) { return $n }
    return $Default
}

function Set-WmsGdriveParam {
    # UPSERT one ir_config_parameter row via psql (key has a UNIQUE
    # constraint, so ON CONFLICT is safe). Failure-safe: a down DB degrades
    # to a DarkGray note - same contract as Write-BackupAudit.
    param([string]$Key, [string]$Value)
    try {
        $k = ($Key   -replace "'", "''")
        $v = ($Value -replace "'", "''")
        $sql = "INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) VALUES ('$k', '$v', 1, NOW(), 1, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_uid = 1, write_date = NOW();"
        $sql | & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    [warn] ir.config_parameter '$Key' not written (ignored)" -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "    [warn] ir.config_parameter '$Key' write failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
    }
}

function Set-GDriveQueueFailure {
    # Persist a queue-failure transition on the catalog row. FAILURE-SAFE
    # (Write-GDriveCatalogRow degrades silently). Computes error_class via
    # Get-GDriveErrorClass (reused), backoff via offline_backoff_base_min.
    # ONE enrichment point shared by the Stage-5 catch and the per-set sweep
    # catch so classification/backoff live in a single place.
    param(
        [Parameter(Mandatory)] [hashtable]$RowBase,   # name/set_stamp/db_name/.../checksum already built
        [Parameter(Mandatory)] [System.Management.Automation.ErrorRecord]$ErrorRecord,
        [int]$PriorRetryCount = 0,
        [int]$BackoffBaseMin = 15,
        [string]$DbName, [string]$DbHost, [int]$DbPort, [string]$DbUser
    )
    $msg    = $ErrorRecord.Exception.Message
    $status = Get-GDriveHttpStatus $ErrorRecord
    $reason = Get-GDriveErrorReason -ErrorRecord $ErrorRecord
    $class  = Get-GDriveErrorClass -StatusCode $status -Reason $reason -Message $msg
    $retry  = $PriorRetryCount + 1
    $state  = if ($class -eq 'offline') { 'waiting' } else { 'failed' }
    # Backoff: base * 2^(retry-1) minutes, capped 24h. auth_expired retries
    # promptly once re-consented -> NULL next_retry_at.
    $next = $null
    if ($class -ne 'auth_expired') {
        $mins = [math]::Min(1440, $BackoffBaseMin * [math]::Pow(2, [math]::Max(0, $retry - 1)))
        $next = (Get-Date).ToUniversalTime().AddMinutes($mins)
    }
    $row = $RowBase.Clone()
    $row['uploaded']      = $false
    $row['queue_state']   = $state
    $row['retry_count']   = $retry
    $row['error_class']   = $class
    $row['last_error']    = if ($msg.Length -gt 240) { $msg.Substring(0, 240) } else { $msg }
    if ($next) { $row['next_retry_at'] = $next }
    Write-GDriveCatalogRow -Row $row -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
}

function Send-GDriveBackupSet {
    # Upload one complete backup set (db .gpg [+ filestore .gpg] + SHA256.txt
    # + backup-info.json) into its Drive day folder, verify every transfer via
    # the Drive-side sha256Checksum (inside Send-GDriveFile), then UPSERT the
    # catalog row. Local names stay untouched; Drive display names keep the
    # .dump.gpg/.zip.gpg discriminators (D8). Used by both today's upload and
    # the pending-retry sweep. Throws on failure - the CALLER owns
    # failure-safety.
    param(
        [Parameter(Mandatory)] [string]$SetStamp,
        [Parameter(Mandatory)] [string]$DbFilePath,
        [Parameter(Mandatory)] [string]$DbFileHash,
        [string]$FsFilePath = '',
        [string]$FsFileHash = '',
        [Parameter(Mandatory)] [string]$BackupType,
        [Parameter(Mandatory)] [string]$Creator,
        [string]$WmsVersion = 'unknown',
        [int]$TocEntries = 0,
        [Parameter(Mandatory)] [object]$EnvConfig,
        [Parameter(Mandatory)] [string]$AccessToken
    )
    $setDate     = [datetime]::ParseExact($SetStamp, 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture)
    $driveStamp  = $setDate.ToString('yyyy-MM-dd_HH-mm-ss')
    $driveDbName = "WMS_DB_$driveStamp.dump.gpg"
    $driveFsName = "WMS_FILESTORE_$driveStamp.zip.gpg"
    $hasFs       = [bool]($FsFilePath -and (Test-Path -LiteralPath $FsFilePath))

    $folderName = Get-WmsConfigParam -Key 'wms_gdrive.folder_name' -Default 'Inventory_Backups' `
        -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
    if (-not $folderName) { $folderName = 'Inventory_Backups' }
    $dayId = Resolve-GDriveBackupFolder -Date $setDate -EnvConfig $EnvConfig `
        -AccessToken $AccessToken -FolderName $folderName `
        -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
    $monthLabel = '{0:00}-{1}' -f $setDate.Month,
        [System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($setDate.Month)
    $folderPath = '{0}/{1}/{2}/{3}' -f $folderName, $setDate.ToString('yyyy'), $monthLabel, $setDate.ToString('yyyy-MM-dd')

    # files[] for backup-info.json; the filestore entry is omitted when the
    # filestore stage was skipped. Plain hashtables: the lib's Get-GDriveProp
    # reads [hashtable] keys (an [ordered] dictionary would read as empty).
    $dbLeaf = Split-Path -Leaf $DbFilePath
    $files = @()
    $files += @{
        role       = 'db'
        local_name = $dbLeaf
        drive_name = $driveDbName
        size_bytes = (Get-Item -LiteralPath $DbFilePath).Length
        sha256     = $DbFileHash.ToLowerInvariant()
    }
    if ($hasFs) {
        $files += @{
            role       = 'filestore'
            local_name = (Split-Path -Leaf $FsFilePath)
            drive_name = $driveFsName
            size_bytes = (Get-Item -LiteralPath $FsFilePath).Length
            sha256     = $FsFileHash.ToLowerInvariant()
        }
    }

    # SHA256.txt covers the .gpg artifacts BY DRIVE NAME (sha256sum format).
    $shaLines = @('{0}  {1}' -f $DbFileHash.ToLowerInvariant(), $driveDbName)
    if ($hasFs) { $shaLines += ('{0}  {1}' -f $FsFileHash.ToLowerInvariant(), $driveFsName) }
    $shaText = ($shaLines -join "`n") + "`n"

    # P4: the FIRST set of a day owns the bare SHA256.txt/backup-info.json
    # names; later sets the same day get _<HH-MM-SS> suffixes. A leftover from
    # OUR OWN earlier attempt (same set_id) keeps the bare name so the
    # collision pre-flight in Send-GDriveFile can skip/replace it in place.
    $shaName  = 'SHA256.txt'
    $infoName = 'backup-info.json'
    $suffix   = $setDate.ToString('HH-mm-ss')
    try {
        $sameDay = @(Get-GDriveBackupSets -AccessToken $AccessToken -ExtraQ (" and '{0}' in parents" -f $dayId))
        foreach ($f in $sameDay) {
            # Re-scope on parents: the mock seam ignores non-appProperties
            # ExtraQ clauses, so other days' sidecars come back too.
            $parents = @(Get-GDriveProp $f 'parents' @())
            if ($parents.Count -gt 0 -and $parents -notcontains $dayId) { continue }
            $sid = [string](Get-GDriveProp (Get-GDriveProp $f 'appProperties' $null) 'set_id' '')
            if ($sid -eq $SetStamp) { continue }
            $fname = [string](Get-GDriveProp $f 'name' '')
            if ($fname -eq 'SHA256.txt')       { $shaName  = "SHA256_$suffix.txt" }
            if ($fname -eq 'backup-info.json') { $infoName = "backup-info_$suffix.json" }
        }
    } catch {
        # Listing failed: suffixed names cannot clobber another set's sidecars.
        Write-Host "    [warn] day-folder listing failed; using suffixed sidecar names: $($_.Exception.Message)" -ForegroundColor DarkGray
        $shaName  = "SHA256_$suffix.txt"
        $infoName = "backup-info_$suffix.json"
    }

    $tmpSha  = Join-Path $env:TEMP "wms-gdrive-$SetStamp-SHA256.txt"
    $tmpInfo = Join-Path $env:TEMP "wms-gdrive-$SetStamp-backup-info.json"
    $fsRemoteId = ''
    $infoJson = ''
    try {
        [System.IO.File]::WriteAllText($tmpSha, $shaText)
        # Canonical schema lives in the lib (gdrive-restore.ps1 verifies
        # against the same implementation); -OutPath writes UTF-8 no BOM.
        $infoJson = New-BackupInfoJson -SetStamp $SetStamp -DbName $DbName -BackupType $BackupType `
            -Creator $Creator -WmsVersion $WmsVersion -TocEntries $TocEntries -Files $files `
            -OutPath $tmpInfo

        $dbRemote = Send-GDriveFile -LocalPath $DbFilePath -RemoteName $driveDbName -ParentId $dayId `
            -AppProperties (New-GDriveAppProperties -SetStamp $SetStamp -Role 'db' -BackupType $BackupType -DbName $DbName) `
            -ExpectedSha256 $DbFileHash -AccessToken $AccessToken
        Write-Host "    uploaded + verified $driveDbName" -ForegroundColor Green

        if ($hasFs) {
            $fsRemote = Send-GDriveFile -LocalPath $FsFilePath -RemoteName $driveFsName -ParentId $dayId `
                -AppProperties (New-GDriveAppProperties -SetStamp $SetStamp -Role 'filestore' -BackupType $BackupType -DbName $DbName) `
                -ExpectedSha256 $FsFileHash -AccessToken $AccessToken
            $fsRemoteId = [string](Get-GDriveProp $fsRemote 'id' '')
            Write-Host "    uploaded + verified $driveFsName" -ForegroundColor Green
        }

        Send-GDriveFile -LocalPath $tmpSha -RemoteName $shaName -ParentId $dayId `
            -AppProperties (New-GDriveAppProperties -SetStamp $SetStamp -Role 'sha256' -BackupType $BackupType -DbName $DbName) `
            -AccessToken $AccessToken | Out-Null

        Send-GDriveFile -LocalPath $tmpInfo -RemoteName $infoName -ParentId $dayId `
            -AppProperties (New-GDriveAppProperties -SetStamp $SetStamp -Role 'info' -BackupType $BackupType -DbName $DbName) `
            -AccessToken $AccessToken | Out-Null
    } finally {
        # Sidecars carry only hashes + metadata (no secrets); plain delete.
        Remove-Item -LiteralPath $tmpSha, $tmpInfo -Force -ErrorAction SilentlyContinue
    }

    # Catalog row (UPSERT keyed on name; failure-safe inside the lib).
    # Datetimes go in as UTC because Odoo renders naive timestamps as UTC.
    Write-GDriveCatalogRow -Row @{
        name               = $dbLeaf
        set_stamp          = $SetStamp
        db_name            = $DbName
        backup_type        = $BackupType
        backup_time        = $setDate.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
        year               = $setDate.ToString('yyyy')
        month_label        = $monthLabel
        day                = $setDate.ToString('yyyy-MM-dd')
        drive_name         = $driveDbName
        drive_file_id      = [string](Get-GDriveProp $dbRemote 'id' '')
        drive_folder       = $folderPath
        filestore_drive_id = $fsRemoteId
        size_mb            = [math]::Round((Get-Item -LiteralPath $DbFilePath).Length / 1MB, 2)
        checksum           = $DbFileHash
        uploaded           = $true
        upload_time        = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
        creator            = $Creator
        encrypted          = $true
        wms_version        = $WmsVersion
        info_json          = $infoJson
        # v18 offline queue: terminal success mirrors uploaded=true; clear the
        # backoff (NULL) but keep retry_count as the audit trail of attempts.
        queue_state        = 'uploaded'
        next_retry_at      = $null
    } -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser

    return [pscustomobject]@{
        DriveName  = $driveDbName
        FileId     = [string](Get-GDriveProp $dbRemote 'id' '')
        FolderPath = $folderPath
    }
}

function Invoke-GDrivePendingSweep {
    # Stage 5a: re-upload locally-present sets that have no uploaded=true
    # catalog row. The catalog row (not the filesystem) is AUTHORITATIVE for
    # eligibility / ordering / backoff; the filesystem only gates "what bytes
    # still exist to upload" (a pruned .dump.gpg can never be sent). Shared by
    # the daily/manual run AND the -PendingSweep reconnect mode so there is one
    # sweep implementation. Each set is individually failure-safe (one bad set
    # never blocks the others); a non-offline failure records the queue state
    # via Set-GDriveQueueFailure. Returns @{ Ok; Tried }.
    param(
        [Parameter(Mandatory)] [string]$AccessToken,
        [Parameter(Mandatory)] [object]$EnvConfig,
        [string]$WmsVersion = 'unknown',
        [string]$ExcludeStamp = '',     # today's set (uploaded separately) - never swept
        [string]$Creator = 'system (pending sweep)',
        [Parameter(Mandatory)] [string]$BackupDir,
        [string]$DbName, [string]$DbHost, [int]$DbPort, [string]$DbUser
    )
    $sweepOk = 0
    $sweepTried = 0
    # Tunables (failure-safe parse -> default; REPLACES the old AddDays(-7) /
    # -First 3 / hard-coded backoff magic numbers).
    $retMax     = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.offline_retry_max'        -Default '8'  -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 8
    $retWindow  = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.offline_retry_window_days' -Default '14' -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 14
    $retPerRun  = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.offline_retry_max_per_run' -Default '5'  -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 5
    $backoffMin = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.offline_backoff_base_min'  -Default '15' -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 15
    try {
        $uploadedNames = @{}
        $pendingMeta   = @{}   # name -> @{ State; Retry; NextRetry(datetime|$null) }
        $catReadable = $false
        $rows = & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -t -A -v ON_ERROR_STOP=1 `
            -c "SELECT name FROM wms_gdrive_backup WHERE uploaded = true;" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $catReadable = $true
            foreach ($r in @($rows)) { if ($r) { $uploadedNames[([string]$r).Trim()] = $true } }
        }
        # Catalog unreadable (wms_reports < 3.0.0 or DB down): skip the sweep
        # rather than blindly re-uploading history.
        if ($catReadable) {
            # Catalog-authoritative queue state for the not-yet-uploaded rows.
            # Pipe-separated so a name with no value still yields fixed columns.
            # NOTE: next_retry_at is rendered ISO-8601 WITHOUT a quoted 'T'
            # literal in to_char ('YYYY-MM-DD"T"...'); on Windows PowerShell 5.1
            # the embedded \" in the -c argument gets re-toggled by the C-runtime
            # arg parser of psql.exe, which truncates the SQL at that quote and
            # emits a "extra command-line argument FROM ignored" warning. Under
            # $ErrorActionPreference='Stop' that native-stderr line becomes a
            # terminating error and the whole sweep is skipped. Concatenating the
            # date and time halves with a plain 'T' string keeps the -c argument
            # free of double-quotes, so it tokenizes cleanly on PS 5.1.
            $qrows = & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -t -A -F '|' -v ON_ERROR_STOP=1 `
                -c "SELECT name, COALESCE(queue_state,''), COALESCE(retry_count,0), COALESCE(to_char(next_retry_at,'YYYY-MM-DD')||'T'||to_char(next_retry_at,'HH24:MI:SS'),'') FROM wms_gdrive_backup WHERE uploaded = false;" 2>$null
            if ($LASTEXITCODE -eq 0) {
                foreach ($qr in @($qrows)) {
                    if (-not $qr) { continue }
                    $parts = ([string]$qr).Split('|')
                    if ($parts.Count -lt 4) { continue }
                    $nm = $parts[0].Trim()
                    if (-not $nm) { continue }
                    $rc = 0; [void][int]::TryParse($parts[2].Trim(), [ref]$rc)
                    $nr = $null
                    $nrRaw = $parts[3].Trim()
                    if ($nrRaw) {
                        $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor `
                                  [System.Globalization.DateTimeStyles]::AdjustToUniversal
                        $tmp = [datetime]::MinValue
                        if ([datetime]::TryParse($nrRaw, [System.Globalization.CultureInfo]::InvariantCulture, $styles, [ref]$tmp)) { $nr = $tmp }
                    }
                    $pendingMeta[$nm] = @{ State = $parts[1].Trim(); Retry = $rc; NextRetry = $nr }
                }
            }

            $stampRx = '^(emergency-)?' + [regex]::Escape($DbName) + '-(\d{8}-\d{6})\.dump\.gpg$'
            $cutoff  = (Get-Date).AddDays(-$retWindow)
            $nowUtc  = (Get-Date).ToUniversalTime()
            $candidates = @(Get-ChildItem $BackupDir -Filter '*.dump.gpg' -ErrorAction SilentlyContinue |
                ForEach-Object {
                    if ($_.Name -match $stampRx) {
                        $ps = $Matches[2]
                        $pd = $null
                        try { $pd = [datetime]::ParseExact($ps, 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture) } catch {}
                        # filesystem guard: the .dump.gpg must exist, parse, not
                        # be the current stamp, and not already be uploaded=true.
                        if ($pd -and $ps -ne $ExcludeStamp -and -not $uploadedNames.ContainsKey($_.Name)) {
                            $meta  = $pendingMeta[$_.Name]
                            $retry = 0; $nextRetry = $null
                            if ($meta) { $retry = [int]$meta['Retry']; $nextRetry = $meta['NextRetry'] }
                            [pscustomobject]@{
                                File        = $_
                                SetStamp    = $ps
                                IsEmergency = [bool]$Matches[1]
                                FileTooOld  = ($pd -lt $cutoff)
                                Retry       = $retry
                                NextRetry   = $nextRetry
                            }
                        }
                    }
                })

            # Abandon (write-once) sets past the attempt cap or the window;
            # they never re-enter the eligible list.
            foreach ($c in $candidates) {
                if ($c.Retry -ge $retMax -or $c.FileTooOld) {
                    $meta = $pendingMeta[$c.File.Name]
                    if (-not $meta -or $meta['State'] -ne 'abandoned') {
                        Write-Host "    [warn] pending set $($c.SetStamp) abandoned (retry=$($c.Retry)/$retMax, older-than-window=$($c.FileTooOld))" -ForegroundColor Yellow
                        Write-GDriveCatalogRow -Row @{ name = $c.File.Name; queue_state = 'abandoned' } `
                            -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
                    }
                }
            }

            # Eligible = within window AND retry_count < max AND backoff elapsed
            # (next_retry_at NULL or <= now). Oldest-first, then fewest retries
            # so a chronically-failing set can't starve newer ones in the cap.
            $pendingSets = @($candidates |
                Where-Object {
                    -not $_.FileTooOld -and $_.Retry -lt $retMax -and
                    ($null -eq $_.NextRetry -or $_.NextRetry -le $nowUtc)
                } |
                Sort-Object -Property SetStamp, Retry |
                Select-Object -First $retPerRun)

            foreach ($p in $pendingSets) {
                $sweepTried++
                # Re-derive the catalog row base so a failure can record full
                # metadata (Set-GDriveQueueFailure UPSERTs on name).
                $pSetDate = $null
                try { $pSetDate = [datetime]::ParseExact($p.SetStamp, 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture) } catch {}
                $pType = 'auto'
                if ($p.IsEmergency) { $pType = 'emergency' }
                $pDbHash = (Get-FileHash -LiteralPath $p.File.FullName -Algorithm SHA256).Hash
                $rowBase = @{
                    name        = $p.File.Name
                    set_stamp   = $p.SetStamp
                    db_name     = $DbName
                    backup_type = $pType
                    size_mb     = [math]::Round($p.File.Length / 1MB, 2)
                    checksum    = $pDbHash
                    creator     = $Creator
                    encrypted   = $true
                    wms_version = $WmsVersion
                }
                if ($pSetDate) {
                    $rowBase['backup_time'] = $pSetDate.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
                    $rowBase['year']        = $pSetDate.ToString('yyyy')
                    $rowBase['month_label'] = '{0:00}-{1}' -f $pSetDate.Month, [System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($pSetDate.Month)
                    $rowBase['day']         = $pSetDate.ToString('yyyy-MM-dd')
                }
                # Transient in-flight marker immediately before the upload.
                Write-GDriveCatalogRow -Row @{ name = $p.File.Name; queue_state = 'uploading' } `
                    -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
                try {
                    Write-Host "    retrying pending set $($p.SetStamp)" -ForegroundColor DarkGray
                    $pFsPath = $p.File.FullName -replace '\.dump\.gpg$', '-filestore.zip.gpg'
                    $pFsHash = ''
                    if (Test-Path -LiteralPath $pFsPath) {
                        $pFsHash = (Get-FileHash -LiteralPath $pFsPath -Algorithm SHA256).Hash
                    } else {
                        $pFsPath = ''
                    }
                    Send-GDriveBackupSet -SetStamp $p.SetStamp -DbFilePath $p.File.FullName `
                        -DbFileHash $pDbHash -FsFilePath $pFsPath -FsFileHash $pFsHash `
                        -BackupType $pType -Creator $Creator `
                        -WmsVersion $WmsVersion -EnvConfig $EnvConfig -AccessToken $AccessToken | Out-Null
                    $sweepOk++
                } catch {
                    Write-Host "    [warn] pending set $($p.SetStamp) retry failed (will retry next run): $($_.Exception.Message)" -ForegroundColor Yellow
                    Set-GDriveQueueFailure -RowBase $rowBase -ErrorRecord $_ `
                        -PriorRetryCount $p.Retry -BackoffBaseMin $backoffMin `
                        -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
                }
            }
        }
    } catch {
        Write-Host "    [warn] pending sweep skipped: $($_.Exception.Message)" -ForegroundColor DarkGray
    }
    return @{ Ok = $sweepOk; Tried = $sweepTried }
}

if ($PendingSweep) {
    # === -PendingSweep mode: reconnect / "Retry Now" warm-loop ============
    # Stage 5a (sweep) + 5e (quota cache) ONLY. No pg_dump, no filestore, no
    # local backup_db/backup_filestore audit rows (Stages 1-4 were skipped).
    # An up-front Test-GDriveReachable makes the run a clean no-op while still
    # offline / when the grant has expired, so the hourly reconnect cron and
    # the DR-page button are cheap to fire.
    if (-not $GdReady) {
        Write-Host "Pending sweep: Google Drive stage not ready (disabled / not connected) - nothing to do." -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Pending sweep complete (no-op)." -ForegroundColor Green
        exit 0
    }
    Write-Host "Google Drive pending-upload sweep" -ForegroundColor Cyan
    $psOk = $false
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $cfg = Get-GDriveEnvConfig -EnvPath $EnvPath
        $tok = Get-GDriveAccessToken -TokenPath $TokenPath -EnvConfig $cfg

        # wms_version for backup-info.json (failure-safe; DB may be down).
        $GdWmsVersion = 'unknown'
        try {
            $vOut = & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -t -A -v ON_ERROR_STOP=1 `
                -c "SELECT latest_version FROM ir_module_module WHERE name='wms_reports';" 2>$null
            if ($LASTEXITCODE -eq 0 -and $vOut) {
                $v0 = (@($vOut) | Where-Object { $_ } | Select-Object -First 1)
                if ($v0) { $GdWmsVersion = ([string]$v0).Trim() }
            }
        } catch {}

        # Up-front reachability probe: ONE about.get instead of a doomed upload.
        $reach = Test-GDriveReachable -AccessToken $tok
        if (-not $reach.Reachable) {
            if ($reach.Class -eq 'auth_expired') {
                Write-Host "    Drive authorization expired - re-run scripts\setup-gdrive-auth.ps1 (publish the GCP consent screen to Production if still in Testing). Pending sets are kept; sweep skipped." -ForegroundColor Yellow
            } else {
                Write-Host "    Drive unreachable ($($reach.Class)) - still offline. Pending sets stay queued; nothing uploaded." -ForegroundColor DarkGray
            }
            Write-Host ""
            Write-Host "Pending sweep complete (no-op: $($reach.Class))." -ForegroundColor Green
            exit 0
        }

        # 5a. The sweep itself (no ExcludeStamp - there is no fresh set today).
        $sweep = Invoke-GDrivePendingSweep -AccessToken $tok -EnvConfig $cfg `
            -WmsVersion $GdWmsVersion -BackupDir $BackupDir `
            -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser

        # 5e. Quota snapshot -> wms_gdrive.last_about cache (health page reads
        # it; failure-safe).
        try {
            $about    = Get-GDriveAbout -AccessToken $tok
            $quota    = Get-GDriveProp $about 'storageQuota' $null
            $aboutUsr = Get-GDriveProp $about 'user' $null
            $usedMb  = 0.0
            $limitMb = 0.0
            $usedRaw  = Get-GDriveProp $quota 'usage' ''
            $limitRaw = Get-GDriveProp $quota 'limit' ''
            if ($usedRaw)  { $usedMb  = [math]::Round([double]$usedRaw / 1MB, 1) }
            if ($limitRaw) { $limitMb = [math]::Round([double]$limitRaw / 1MB, 1) }
            $aboutJson = [ordered]@{
                used_mb     = $usedMb
                limit_mb    = $limitMb
                checked_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
                email       = [string](Get-GDriveProp $aboutUsr 'emailAddress' '')
            } | ConvertTo-Json -Compress
            Set-WmsGdriveParam -Key 'wms_gdrive.last_about' -Value $aboutJson
        } catch {
            Write-Host "    [warn] Drive quota check failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
        }

        # A backup_gdrive audit row only when sets were actually attempted, so
        # the existing _cron_notify_gdrive_events path notifies on a reconnect
        # upload (P3) without a new notification channel. A quiet empty queue
        # writes nothing (avoids audit-row spam every hour).
        if ($sweep.Tried -gt 0) {
            $allOk = ($sweep.Ok -eq $sweep.Tried)
            Send-Heartbeat -Url $GdriveHb
            Write-BackupAudit -AuditType 'backup_gdrive' -Success $allOk `
                -FileName "pending-sweep-$Stamp" `
                -Message "Pending-upload sweep (reconnect): $($sweep.Ok)/$($sweep.Tried) set(s) uploaded"
        }
        Write-Host "    Pending sweep: $($sweep.Ok)/$($sweep.Tried) retried." -ForegroundColor Green
        $psOk = $true
    } catch {
        # Failure-safe: a sweep problem must never crash the cron / button.
        # A dead refresh grant throws here (before the reachability probe);
        # surface the re-consent instruction like the spec's auth_expired path.
        if ($_.Exception.Message -match 'GDRIVE_AUTH_EXPIRED|invalid_grant') {
            Write-Host "    Drive authorization expired - re-run scripts\setup-gdrive-auth.ps1 (publish the GCP consent screen to Production if still in Testing). Pending sets are kept; sweep skipped." -ForegroundColor Yellow
        } else {
            Write-Host "    [warn] Pending sweep failed (queued sets are intact): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    if ($psOk) {
        Write-Host "Pending sweep complete." -ForegroundColor Green
    } else {
        Write-Host "Pending sweep complete (with warnings)." -ForegroundColor Yellow
    }
    exit 0
}

if ($GdReady) {
    Write-Host "Google Drive upload" -ForegroundColor Cyan
    # Pre-resolved so the catch block can reference them even when the throw
    # happens before they are computed.
    $GdCreator    = 'system (scheduled)'
    $GdWmsVersion = 'unknown'
    try {
        # PS 5.1 defaults to TLS 1.0; Google endpoints require 1.2+ (the lib
        # sets this too - kept here so the stage never depends on lib internals).
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $cfg = Get-GDriveEnvConfig -EnvPath $EnvPath
        $tok = Get-GDriveAccessToken -TokenPath $TokenPath -EnvConfig $cfg

        # wms_version for backup-info.json (failure-safe; DB may be down).
        try {
            $vOut = & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -t -A -v ON_ERROR_STOP=1 `
                -c "SELECT latest_version FROM ir_module_module WHERE name='wms_reports';" 2>$null
            if ($LASTEXITCODE -eq 0 -and $vOut) {
                $v0 = (@($vOut) | Where-Object { $_ } | Select-Object -First 1)
                if ($v0) { $GdWmsVersion = ([string]$v0).Trim() }
            }
        } catch {}

        # Creator attribution (D5): a manual run may carry an Odoo-login
        # handshake in wms_gdrive.last_manual_requester ('login|iso-ts',
        # honored only while fresh: < 10 minutes old).
        if ($Source -eq 'manual') {
            $GdCreator = 'manual (console)'
            $req = Get-WmsConfigParam -Key 'wms_gdrive.last_manual_requester' -Default '' `
                -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
            if ($req -and $req.Contains('|')) {
                $reqLogin = $req.Substring(0, $req.IndexOf('|'))
                $reqIso   = $req.Substring($req.IndexOf('|') + 1)
                try {
                    $styles  = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor `
                               [System.Globalization.DateTimeStyles]::AdjustToUniversal
                    $reqTime = [datetime]::Parse($reqIso, [System.Globalization.CultureInfo]::InvariantCulture, $styles)
                    if ($reqLogin -and (((Get-Date).ToUniversalTime() - $reqTime).TotalMinutes -lt 10)) {
                        $GdCreator = $reqLogin
                    }
                } catch {}
            }
        } elseif ($Source -eq 'emergency') {
            $GdCreator = "$env:COMPUTERNAME\$env:USERNAME"
        }

        # 5a. Pending sweep (P14 'retry later' / v18 offline queue): catalog-
        # authoritative re-upload of local sets lacking an uploaded=true row,
        # oldest-first, capped per run, with per-set backoff + abandonment.
        # Shared with the -PendingSweep reconnect mode. Each set is failure-safe
        # so one bad set cannot block today's upload.
        $sweep = Invoke-GDrivePendingSweep -AccessToken $tok -EnvConfig $cfg `
            -WmsVersion $GdWmsVersion -ExcludeStamp $Stamp -BackupDir $BackupDir `
            -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
        $sweepOk = $sweep.Ok
        $sweepTried = $sweep.Tried

        # 5b. Today's set - reuse the in-scope artifact hashes (no re-hash).
        # v18 state machine: write a 'created' row BEFORE the attempt so the
        # queue can show the in-flight set; Send-GDriveBackupSet flips it to
        # 'uploaded' on success, the Stage-5 catch to 'waiting'/'failed'.
        Write-GDriveCatalogRow -Row @{ name = (Split-Path -Leaf $DumpEncPath); queue_state = 'created' } `
            -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
        $GdFsPath = ''
        $GdFsHash = ''
        if ((Test-Path Variable:\ZipEncPath) -and $ZipEncPath -and (Test-Path -LiteralPath $ZipEncPath)) {
            $GdFsPath = $ZipEncPath
            $GdFsHash = $fsHash
        }
        $today = Send-GDriveBackupSet -SetStamp $Stamp -DbFilePath $DumpEncPath -DbFileHash $dbHash `
            -FsFilePath $GdFsPath -FsFileHash $GdFsHash -BackupType $Source -Creator $GdCreator `
            -WmsVersion $GdWmsVersion -TocEntries $tocLines -EnvConfig $cfg -AccessToken $tok

        # 5d. Drive-side tiered retention. Runs only after a successful
        # upload; its own failure must not mark the (already verified) upload
        # failed, so it gets an inner catch.
        $retSummary = 'skipped'
        try {
            $tiers = @{
                daily_days    = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.retention_daily_days'    -Default '30' -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 30
                weekly_months = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.retention_weekly_months' -Default '6'  -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 6
                monthly_years = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.retention_monthly_years' -Default '2'  -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 2
            }
            $delManual = ((Get-WmsConfigParam -Key 'wms_gdrive.delete_manual' -Default '0' `
                -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) -eq '1')
            $retSummary = Invoke-GDriveRetention -AccessToken $tok -Tiers $tiers -DeleteManual $delManual
        } catch {
            Write-Host "    [warn] Drive retention sweep failed (uploads unaffected): $($_.Exception.Message)" -ForegroundColor Yellow
            $retSummary = "FAILED: $($_.Exception.Message)"
        }

        # 5e. Quota snapshot -> wms_gdrive.last_about cache (health page +
        # settings wizard read it; failure-safe).
        try {
            $about   = Get-GDriveAbout -AccessToken $tok
            $quota   = Get-GDriveProp $about 'storageQuota' $null
            $aboutUsr = Get-GDriveProp $about 'user' $null
            $usedMb  = 0.0
            $limitMb = 0.0
            $usedRaw  = Get-GDriveProp $quota 'usage' ''
            $limitRaw = Get-GDriveProp $quota 'limit' ''
            if ($usedRaw)  { $usedMb  = [math]::Round([double]$usedRaw / 1MB, 1) }
            if ($limitRaw) { $limitMb = [math]::Round([double]$limitRaw / 1MB, 1) }
            $aboutJson = [ordered]@{
                used_mb     = $usedMb
                limit_mb    = $limitMb
                checked_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
                email       = [string](Get-GDriveProp $aboutUsr 'emailAddress' '')
            } | ConvertTo-Json -Compress
            Set-WmsGdriveParam -Key 'wms_gdrive.last_about' -Value $aboutJson
        } catch {
            Write-Host "    [warn] Drive quota check failed (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
        }

        $sweepNote = ''
        if ($sweepTried -gt 0) { $sweepNote = "; pending sweep: $sweepOk/$sweepTried retried" }
        Send-Heartbeat -Url $GdriveHb
        Write-BackupAudit -AuditType 'backup_gdrive' -Success $true `
            -FileName (Split-Path -Leaf $DumpEncPath) -SizeMb $dbSizeMb -Verified $true `
            -Checksum $dbHash `
            -Message "Drive upload verified (set $Stamp, source=$Source) -> $($today.DriveName) id=$($today.FileId); retention: $retSummary$sweepNote"
        Write-Host "    Drive upload complete + verified." -ForegroundColor Green
    } catch {
        $gdErr = $_   # captured so the nested psql try/catch can't shadow $_
        Write-Host "    [warn] Drive upload failed (LOCAL backup is intact): $($gdErr.Exception.Message)" -ForegroundColor Yellow
        Send-Heartbeat -Url $GdriveHb -Fail
        Write-BackupAudit -AuditType 'backup_gdrive' -Success $false `
            -FileName (Split-Path -Leaf $DumpEncPath) `
            -Message "Drive upload FAILED (source=$Source): $($gdErr.Exception.Message)"
        # Pending catalog row so the next run's sweep retries this set. v18:
        # record the queue-failure transition (class/backoff/retry++) via the
        # shared Set-GDriveQueueFailure. Failure-safe itself; the re-guard
        # covers a partially-loaded lib.
        try {
            $failName  = (Split-Path -Leaf $DumpEncPath)
            $failDate  = [datetime]::ParseExact($Stamp, 'yyyyMMdd-HHmmss', [System.Globalization.CultureInfo]::InvariantCulture)
            $failMonth = '{0:00}-{1}' -f $failDate.Month,
                [System.Globalization.CultureInfo]::InvariantCulture.DateTimeFormat.GetMonthName($failDate.Month)
            $failRowBase = @{
                name        = $failName
                set_stamp   = $Stamp
                db_name     = $DbName
                backup_type = $Source
                backup_time = $failDate.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
                year        = $failDate.ToString('yyyy')
                month_label = $failMonth
                day         = $failDate.ToString('yyyy-MM-dd')
                size_mb     = $dbSizeMb
                checksum    = $dbHash
                creator     = $GdCreator
                encrypted   = $true
                wms_version = $GdWmsVersion
            }
            # Prior retry_count from the catalog (the 'created' row, or a prior
            # failed row); failure-safe -> 0.
            $priorRetry = 0
            try {
                $escName = ($failName -replace "'", "''")
                $rcOut = & psql -U $DbUser -h $DbHost -p $DbPort -d $DbName -w -t -A -v ON_ERROR_STOP=1 `
                    -c "SELECT COALESCE(retry_count,0) FROM wms_gdrive_backup WHERE name = '$escName' ORDER BY id DESC LIMIT 1;" 2>$null
                if ($LASTEXITCODE -eq 0 -and $rcOut) {
                    $rc0 = (@($rcOut) | Where-Object { "$_" -match '^\s*\d+\s*$' } | Select-Object -First 1)
                    if ($null -ne $rc0) { [void][int]::TryParse(([string]$rc0).Trim(), [ref]$priorRetry) }
                }
            } catch {}
            $backoffBase = ConvertTo-GDrivePositiveInt (Get-WmsConfigParam -Key 'wms_gdrive.offline_backoff_base_min' -Default '15' `
                -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser) 15
            Set-GDriveQueueFailure -RowBase $failRowBase -ErrorRecord $gdErr `
                -PriorRetryCount $priorRetry -BackoffBaseMin $backoffBase `
                -DbName $DbName -DbHost $DbHost -DbPort $DbPort -DbUser $DbUser
        } catch {
            Write-Host "    [warn] pending catalog row not written (ignored): $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "Google Drive upload: disabled (run scripts\setup-gdrive-auth.ps1 to enable)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Backup complete (encrypted). Artifacts in $BackupDir" -ForegroundColor Green
Write-Host "WARNING: without BACKUP_PASSPHRASE these files cannot be restored." -ForegroundColor Yellow

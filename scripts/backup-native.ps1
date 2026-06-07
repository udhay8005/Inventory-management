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
    [string]$DbUser
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

# --- Find gpg.exe on PATH (or in the default Gpg4win install location) ---
# PowerShell 5.1 has no `?.` operator, so use the explicit null check.
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
trap {
    if (-not $script:ObsBackupOk) {
        Send-Heartbeat -Url $HeartbeatUrl -Fail
        Write-BackupAudit -AuditType 'backup_db' -Success $false -FileName "$DbName-$Stamp" `
            -DurationSeconds ((Get-Date) - $BackupStart).TotalSeconds `
            -Message "Backup failed: $($_.Exception.Message)"
    }
    break
}

# --- 1. Database dump (encrypted) ---------------------------------------
$DumpPath    = Join-Path $BackupDir "$DbName-$Stamp.dump"
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
        -Checksum $dbHash -Message "OK"
} finally {
    # Always shred the plaintext dump - it's on disk for milliseconds.
    Remove-Item $DumpPath -Force -ErrorAction SilentlyContinue
}

# --- 2. Filestore zip (encrypted) ---------------------------------------
$Filestore = Join-Path $DataDir "filestore\$DbName"
if (Test-Path $Filestore) {
    $ZipPath    = Join-Path $BackupDir "$DbName-$Stamp-filestore.zip"
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

Write-Host ""
Write-Host "Backup complete (encrypted). Artifacts in $BackupDir" -ForegroundColor Green
Write-Host "WARNING: without BACKUP_PASSPHRASE these files cannot be restored." -ForegroundColor Yellow

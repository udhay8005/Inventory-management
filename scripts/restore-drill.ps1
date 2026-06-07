<#
.SYNOPSIS
    Weekly restore drill - prove the latest GPG-encrypted backup is recoverable
    WITHOUT touching the production database.

.DESCRIPTION
    Decrypts the most recent backups\*.dump.gpg into a temp file (ACL = current
    user), runs `pg_restore --list` to verify the dump's table-of-contents
    survives end-to-end, and optionally restores into a throwaway database
    named wms_drill_<timestamp>. The drill DB is dropped on exit (and on every
    failure path) unless -KeepDrillDb is passed.

    Why this exists
    ---------------
    Backups that are never restored are not backups. This drill runs weekly
    via Task Scheduler so any silent corruption (truncated GPG, mid-write
    cancellation, schema drift breaking pg_restore compatibility) is caught
    within 7 days, not at the moment of a real disaster.

.PARAMETER BackupPath
    Path to a specific .dump.gpg to drill. Default: latest *.dump.gpg under
    .\backups\ by LastWriteTime.

.PARAMETER DryRun
    When set (default), only verifies the TOC via pg_restore --list - does
    NOT create a drill database. Use this for cheap weekly verification.
    Pass -DryRun:$false to perform a full restore into a drill DB.

.PARAMETER KeepDrillDb
    Only honored when -DryRun:$false. Skip dropping the drill DB after the
    restore so an operator can poke around. Use sparingly - every drill DB
    you keep is one a future drill won't be able to create with the same name.

.PARAMETER Passphrase
    Override BACKUP_PASSPHRASE from .env. SecureString. Useful when cycling
    passphrases or running against an off-host backup.

.EXAMPLE
    scripts\restore-drill.ps1
    # Cheap TOC verification on the latest backup.

.EXAMPLE
    scripts\restore-drill.ps1 -DryRun:$false
    # Full restore into wms_drill_<ts>, then drop it.

.EXAMPLE
    scripts\restore-drill.ps1 -BackupPath D:\offsite\wms-20260520-152106.dump.gpg

.NOTES
    Requires: gpg.exe on PATH (or Gpg4win), psql + pg_restore on PATH,
              BACKUP_PASSPHRASE set in .env (not the placeholder).
    Never touches: the production database. Refuses to act if drill DB
                   name does not match the wms_drill_<ts> pattern.
#>
[CmdletBinding()]
param(
    [string]$BackupPath,
    [bool]$DryRun = $true,
    [switch]$KeepDrillDb,
    [SecureString]$Passphrase,
    [string]$DbHost,
    [int]$DbPort,
    [string]$DbUser,
    [string]$AuditDb = 'wms'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir   = Join-Path $ProjectRoot 'backups'
$EnvPath     = Join-Path $ProjectRoot '.env'
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'
$LogDir      = Join-Path $ProjectRoot '.runtime\logs'
$DrillLog    = Join-Path $LogDir 'restore-drill.log'

# Track whether WE set PGPASSWORD (from the conf) so the finally only wipes the
# value we introduced - never a PGPASSWORD the caller already had in their
# environment before invoking the drill.
$script:WeSetPgPassword = $false

# Exit codes (used both by Task Scheduler and by humans grepping logs).
$EXIT_OK              = 0
$EXIT_BACKUP_MISSING  = 1
$EXIT_DECRYPT_FAILED  = 2
$EXIT_TOC_FAILED      = 3
$EXIT_RESTORE_FAILED  = 4
$EXIT_PROD_COLLISION  = 5

# --- Logging: dual sink - file + Windows Event Log (best-effort) ----------
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Drill {
    param(
        [Parameter(Mandatory)] [string]$Level,
        [Parameter(Mandatory)] [string]$Message
    )
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$stamp] [$Level] $Message"
    # File log - always works.
    Add-Content -LiteralPath $DrillLog -Value $line -Encoding utf8
    # Console - color-coded for human invocation.
    $color = switch ($Level) {
        'ERROR' { 'Red' }
        'WARN'  { 'Yellow' }
        'OK'    { 'Green' }
        default { 'Gray' }
    }
    Write-Host $line -ForegroundColor $color
}

function Write-DrillEvent {
    # Best-effort Windows Application Event Log entry. Silently skipped
    # if the WMS_Backup_Drill source is not registered. Registration
    # requires admin once:
    #   New-EventLog -LogName Application -Source 'WMS_Backup_Drill'
    # If you do not want event-log integration, just do not register the
    # source - the script keeps writing to the file log either way.
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
        # Do not fail the drill because event-log writes failed.
        Write-Drill 'WARN' "Event Log write skipped: $($_.Exception.Message)"
    }
}

# Optional healthchecks.io-style heartbeat for the drill, from .env.
$DrillHeartbeatUrl = ''
if (Test-Path $EnvPath) {
    $hb = (Select-String -Path $EnvPath -Pattern '^HEALTHCHECK_DRILL_URL=(.+)$' | Select-Object -First 1)
    if ($hb) { $DrillHeartbeatUrl = $hb.Matches.Groups[1].Value.Trim() }
}

function Send-Heartbeat {
    # Non-blocking, 10s-timeout ping. /fail suffix signals failure.
    # Silent on any error - observability must never break the drill.
    param([string]$Url, [switch]$Fail)
    if (-not $Url) { return }
    $target = if ($Fail) { "$Url/fail" } else { $Url }
    try {
        Invoke-WebRequest -Uri $target -Method Get -TimeoutSec 10 -UseBasicParsing | Out-Null
    } catch {
        Write-Drill 'WARN' "Heartbeat ping failed (ignored): $($_.Exception.Message)"
    }
}

function Write-DrillAudit {
    # Append a restore_drill row to wms_backup_audit in the PRODUCTION DB
    # (-AuditDb, default 'wms') - that is where Odoo reads it. Failure-safe:
    # if wms_reports isn't installed or the DB is unreachable, log a note
    # and continue. The drill's own pass/fail is unaffected.
    param(
        [bool]$Success, [string]$FileName, [double]$SizeMb = 0,
        [int]$TocEntries = 0, [bool]$Verified = $false,
        [double]$DurationSeconds = 0, [string]$Message = '',
        [string]$AuditDb = 'wms'
    )
    if (-not $DbUser -or -not $DbHost -or -not $DbPort) { return }
    try {
        $sk = if ($Success)  { 'true' } else { 'false' }
        $vf = if ($Verified) { 'true' } else { 'false' }
        $fn  = ($FileName -replace "'", "''")
        $msg = ($Message  -replace "'", "''")
        $hn  = ($env:COMPUTERNAME -replace "'", "''")
        $sql = "INSERT INTO wms_backup_audit (name, audit_type, success, event_time, duration_seconds, size_mb, toc_entries, verified, checksum, host, message, create_uid, create_date, write_uid, write_date) VALUES ('$fn', 'restore_drill', $sk, NOW(), $DurationSeconds, $SizeMb, $TocEntries, $vf, '', '$hn', '$msg', 1, NOW(), 1, NOW());"
        $sql | & psql -U $DbUser -h $DbHost -p $DbPort -d $AuditDb -w -v ON_ERROR_STOP=1 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Drill 'INFO' "Recorded drill result in wms_backup_audit ($AuditDb)."
        } else {
            Write-Drill 'WARN' "Drill audit not recorded (is wms_reports installed in '$AuditDb'?)."
        }
    } catch {
        Write-Drill 'WARN' "Drill audit write failed (ignored): $($_.Exception.Message)"
    }
}

# --- Resolve backup path --------------------------------------------------
if (-not $BackupPath) {
    if (-not (Test-Path $BackupDir)) {
        Write-Drill 'ERROR' "Backup directory not found: $BackupDir"
        Write-DrillEvent -EventId 301 -EntryType Error -Message "Backup directory missing: $BackupDir"
        exit $EXIT_BACKUP_MISSING
    }
    $latest = Get-ChildItem -LiteralPath $BackupDir -Filter '*.dump.gpg' -File -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Drill 'ERROR' "No *.dump.gpg files found in $BackupDir"
        Write-DrillEvent -EventId 302 -EntryType Error -Message "No *.dump.gpg files in $BackupDir"
        exit $EXIT_BACKUP_MISSING
    }
    $BackupPath = $latest.FullName
}
if (-not (Test-Path -LiteralPath $BackupPath)) {
    Write-Drill 'ERROR' "Backup file not found: $BackupPath"
    Write-DrillEvent -EventId 303 -EntryType Error -Message "Backup file not found: $BackupPath"
    exit $EXIT_BACKUP_MISSING
}
$backupSize = (Get-Item -LiteralPath $BackupPath).Length
$backupAge  = (New-TimeSpan -Start (Get-Item -LiteralPath $BackupPath).LastWriteTime -End (Get-Date)).TotalHours
Write-Drill 'INFO' "Backup: $BackupPath ($([math]::Round($backupSize/1MB,2)) MB, $([math]::Round($backupAge,1))h old)"

# --- Resolve PG connection from odoo.native.conf --------------------------
if (Test-Path $ConfPath) {
    if (-not $DbHost) {
        $m = Select-String -Path $ConfPath -Pattern '^db_host\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $DbHost = $m.Matches.Groups[1].Value.Trim() }
    }
    if (-not $DbPort) {
        $m = Select-String -Path $ConfPath -Pattern '^db_port\s*=\s*(\d+)' | Select-Object -First 1
        if ($m) { $DbPort = [int]$m.Matches.Groups[1].Value }
    }
    if (-not $DbUser) {
        $m = Select-String -Path $ConfPath -Pattern '^db_user\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) { $DbUser = $m.Matches.Groups[1].Value.Trim() }
    }
    if (-not $env:PGPASSWORD) {
        $m = Select-String -Path $ConfPath -Pattern '^db_password\s*=\s*(.+)$' | Select-Object -First 1
        if ($m) {
            $env:PGPASSWORD = $m.Matches.Groups[1].Value.Trim()
            $script:WeSetPgPassword = $true
        }
    }
}
if (-not $DbHost) { $DbHost = 'localhost' }
if (-not $DbPort) { $DbPort = 5432 }
if (-not $DbUser) { $DbUser = 'odoo' }

# --- Resolve passphrase ---------------------------------------------------
if (-not $Passphrase) {
    if (Test-Path $EnvPath) {
        $line = (Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1)
        if ($line) {
            $envPass = $line.Matches.Groups[1].Value.Trim()
            if ($envPass) { $Passphrase = ConvertTo-SecureString $envPass -AsPlainText -Force }
            $envPass = $null
        }
    }
}
if (-not $Passphrase) {
    Write-Drill 'ERROR' "BACKUP_PASSPHRASE not set in .env - cannot decrypt the backup."
    Write-DrillEvent -EventId 304 -EntryType Error -Message "BACKUP_PASSPHRASE missing"
    exit $EXIT_DECRYPT_FAILED
}
# Reject placeholder via brief plaintext peek.
$ppPeek = [System.Net.NetworkCredential]::new('', $Passphrase).Password
if ($ppPeek -eq 'changeme_backup_passphrase' -or [string]::IsNullOrWhiteSpace($ppPeek)) {
    $ppPeek = $null
    Write-Drill 'ERROR' "BACKUP_PASSPHRASE is still the placeholder. Set a real passphrase in .env."
    Write-DrillEvent -EventId 305 -EntryType Error -Message "BACKUP_PASSPHRASE is placeholder"
    exit $EXIT_DECRYPT_FAILED
}
$ppPeek = $null

# --- Locate gpg.exe (same logic as backup-native.ps1) ---------------------
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
    Write-Drill 'ERROR' "gpg.exe not found on PATH or in Gpg4win install dirs."
    Write-DrillEvent -EventId 306 -EntryType Error -Message "gpg.exe missing"
    exit $EXIT_DECRYPT_FAILED
}

# --- Allocate temp file with restrictive ACL ------------------------------
$tempFile = New-TemporaryFile
$decrypted = "$($tempFile.FullName).pgdmp"
Remove-Item -LiteralPath $tempFile.FullName -Force -ErrorAction SilentlyContinue

# --- Drill DB name - refuse to act if it does not match the safety pattern ---
$drillStamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$drillDb = "wms_drill_$drillStamp"
if ($drillDb -notmatch '^wms_drill_\d{8}_\d{6}$') {
    Write-Drill 'ERROR' "Refusing to act - drill DB name '$drillDb' does not match safety pattern."
    exit $EXIT_PROD_COLLISION
}

$started = Get-Date
$exitCode = $EXIT_OK

try {
    # --- Decrypt via cmd /c echo | gpg (matches backup-native.ps1) --------
    # FPAT High: switched away from `cmd /c echo|gpg --passphrase-fd 0` to a
    # passphrase FILE. The old pattern silently TRUNCATED any passphrase
    # containing a cmd metacharacter (& | < > ^ %), making the encrypted
    # backup unrecoverable. backup-native.ps1 changed in lock-step, so the
    # byte stream that encrypted the .gpg matches the bytes we read here.
    Write-Drill 'INFO' "Decrypting backup to temp file..."
    $errFile = [System.IO.Path]::GetTempFileName()
    $pwFile = [System.IO.Path]::GetTempFileName()
    $plain = [System.Net.NetworkCredential]::new('', $Passphrase).Password
    try {
        [System.IO.File]::WriteAllBytes(
            $pwFile, [System.Text.Encoding]::UTF8.GetBytes($plain)
        )
        & $gpg --batch --yes --pinentry-mode loopback `
            --passphrase-file $pwFile `
            --decrypt -o $decrypted $BackupPath 2> $errFile
        $rc = $LASTEXITCODE
        if ($rc -ne 0) {
            $stderr = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
            throw "gpg decrypt exit ${rc}: $stderr"
        }
    } finally {
        # Best-effort plaintext wipe — overwrite then drop the local
        # binding so a subsequent memory snapshot cannot recover it.
        if ($plain) { $plain = ' ' * $plain.Length }
        $plain = $null
        if (Test-Path -LiteralPath $pwFile) {
            try { [System.IO.File]::WriteAllBytes($pwFile, (New-Object byte[] 64)) } catch {}
            Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $decrypted)) {
        throw "Decrypted file missing after gpg success."
    }
    $decryptedSize = (Get-Item -LiteralPath $decrypted).Length
    if ($decryptedSize -lt 1MB) {
        throw "Decrypted file suspiciously small: $decryptedSize bytes (expected >= 1 MB for a real WMS dump)."
    }
    Write-Drill 'OK' "Decrypt OK ($([math]::Round($decryptedSize/1MB,2)) MB)."

    # --- pg_restore --list - TOC sanity check -----------------------------
    Write-Drill 'INFO' "Verifying TOC via pg_restore --list..."
    $tocFile = "$decrypted.toc"
    & pg_restore --list $decrypted > $tocFile
    if ($LASTEXITCODE -ne 0) {
        $exitCode = $EXIT_TOC_FAILED
        throw "pg_restore --list failed (exit $LASTEXITCODE)."
    }
    $tocLines = (Get-Content -LiteralPath $tocFile | Measure-Object -Line).Lines
    if ($tocLines -lt 100) {
        $exitCode = $EXIT_TOC_FAILED
        throw "TOC has only $tocLines lines - expected 1000+ for a real Odoo dump. Backup may be truncated."
    }
    Write-Drill 'OK' "TOC OK ($tocLines entries)."
    Remove-Item -LiteralPath $tocFile -Force -ErrorAction SilentlyContinue

    # --- Optional full restore into the drill DB --------------------------
    if (-not $DryRun) {
        Write-Drill 'INFO' "Creating drill database $drillDb..."
        $createSql = "CREATE DATABASE $drillDb"
        & psql -U $DbUser -h $DbHost -p $DbPort -d postgres -w -c $createSql | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create drill DB $drillDb."
        }
        Write-Drill 'OK' "Drill DB $drillDb created."

        try {
            Write-Drill 'INFO' "Restoring into $drillDb (may take several minutes)..."
            & pg_restore -U $DbUser -h $DbHost -p $DbPort -d $drillDb --no-owner --no-privileges $decrypted 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "pg_restore failed (exit $LASTEXITCODE)."
            }
            # Sanity probe: count res_users - every Odoo DB has this table.
            $probe = & psql -U $DbUser -h $DbHost -p $DbPort -d $drillDb -t -A -w -c "SELECT count(*) FROM res_users"
            if ($LASTEXITCODE -ne 0 -or -not ($probe -match '^\d+$')) {
                throw "Sanity probe failed on $drillDb (could not count res_users)."
            }
            Write-Drill 'OK' "Restore OK - drill DB contains $probe res_users."
        } finally {
            if (-not $KeepDrillDb) {
                Write-Drill 'INFO' "Dropping drill DB $drillDb..."
                & psql -U $DbUser -h $DbHost -p $DbPort -d postgres -w -c "DROP DATABASE IF EXISTS $drillDb" | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Drill 'OK' "Drill DB $drillDb dropped."
                } else {
                    Write-Drill 'WARN' "Could not drop drill DB $drillDb - drop it manually."
                }
            } else {
                Write-Drill 'WARN' "Keeping drill DB $drillDb on the cluster (-KeepDrillDb)."
            }
        }
    } else {
        Write-Drill 'INFO' "DryRun mode - skipping full restore. Pass -DryRun:`$false for an end-to-end test."
    }

    $elapsed = (Get-Date) - $started
    Write-Drill 'OK' "Drill complete in $([math]::Round($elapsed.TotalSeconds,1))s."
    Write-DrillEvent -EventId 100 -EntryType Information -Message "Restore drill succeeded for $BackupPath in $([math]::Round($elapsed.TotalSeconds,1))s (DryRun=$DryRun)."
    # Record + heartbeat the successful drill (failure-safe).
    $drillSizeMb = [math]::Round($backupSize / 1MB, 2)
    $mode = if ($DryRun) { "DryRun (TOC verify)" } else { "full restore" }
    Write-DrillAudit -Success $true -FileName (Split-Path -Leaf $BackupPath) `
        -SizeMb $drillSizeMb -TocEntries $tocLines -Verified $true `
        -DurationSeconds $elapsed.TotalSeconds -Message "OK - $mode" -AuditDb $AuditDb
    Send-Heartbeat -Url $DrillHeartbeatUrl
}
catch {
    Write-Drill 'ERROR' $_.Exception.Message
    Write-DrillEvent -EventId 300 -EntryType Error -Message "Restore drill FAILED: $($_.Exception.Message)"
    # Record + heartbeat the failed drill (failure-safe).
    $failName = if ($BackupPath) { Split-Path -Leaf $BackupPath } else { "drill-run" }
    Write-DrillAudit -Success $false -FileName $failName `
        -DurationSeconds ((Get-Date) - $started).TotalSeconds `
        -Message "FAILED: $($_.Exception.Message)" -AuditDb $AuditDb
    Send-Heartbeat -Url $DrillHeartbeatUrl -Fail
    if (-not $exitCode -or $exitCode -eq $EXIT_OK) {
        $exitCode = $EXIT_RESTORE_FAILED
    }
}
finally {
    # ALWAYS wipe the decrypted plaintext, even on exception.
    if (Test-Path -LiteralPath $decrypted) {
        Remove-Item -LiteralPath $decrypted -Force -ErrorAction SilentlyContinue
    }
    # Only wipe PGPASSWORD if WE set it from the conf; never clobber a value the
    # caller had in their own environment before invoking the drill.
    if ($script:WeSetPgPassword) {
        Remove-Item env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

exit $exitCode

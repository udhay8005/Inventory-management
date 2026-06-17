<#
.SYNOPSIS
    Restore an encrypted WMS backup created by scripts\backup-native.ps1.

.DESCRIPTION
    Decrypts a `*.dump.gpg` file with BACKUP_PASSPHRASE from .env (or
    -Passphrase), then pg_restore into the target database. If a
    matching `-filestore.zip.gpg` sits next to the dump it is also
    decrypted + extracted on top of the data_dir.

    Safety: by default refuses to overwrite an existing database. Pass
    -Force to drop + recreate.

    Google Drive-sourced backups: scripts\gdrive-restore.ps1 downloads a
    Drive set, verifies it (SHA-256 + GPG envelope), renames it back to
    the local convention and can orchestrate this script end-to-end
    (-AutoRestore: emergency backup, service stop/start, integrity probes).

.PARAMETER BackupFile
    Path to the `*.dump.gpg` to restore. The matching
    `-filestore.zip.gpg` is auto-detected from the same folder.

.PARAMETER DbName
    Target database name. Default: wms.

.PARAMETER Passphrase
    Override the .env BACKUP_PASSPHRASE for this run only.

.PARAMETER Force
    Drop the target database first if it already exists. WITHOUT this,
    the script refuses to overwrite live data.

.EXAMPLE
    scripts\restore-native.ps1 -BackupFile .\backups\wms-20260520-080000.dump.gpg
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$BackupFile,
    [string]$DbName = 'wms',
    [SecureString]$Passphrase,
    [switch]$Force,
    [string]$DbHost,
    [int]$DbPort,
    [string]$DbUser
)

# --- Identifier safety -----------------------------------------------------
# $DbName is interpolated UNPARAMETERIZED into psql -c SQL (DROP/CREATE
# DATABASE) further down, so it MUST be a safe Postgres identifier. Validate
# it BEFORE any SQL is built: this blocks injection (e.g. a name containing
# '; DROP DATABASE wms', which psql -c would run as extra statements) and the
# silent breakage of unquoted identifiers (hyphens, uppercase folding to
# lowercase). -cnotmatch is case-SENSITIVE so uppercase is rejected; valid
# names like 'wms' and 'wms_restore_20260612_163000' still pass.
if ($DbName -cnotmatch '^[a-z_][a-z0-9_]{0,62}$') {
    Write-Host "Invalid -DbName '$DbName': must be a lowercase Postgres identifier (letters, digits, underscores; start with a letter or underscore; max 63 chars)." -ForegroundColor Red
    exit 1
}

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DataDir     = Join-Path $ProjectRoot '.runtime\data'
$EnvPath     = Join-Path $ProjectRoot '.env'
$ConfPath    = Join-Path $ProjectRoot 'config\odoo.native.conf'

# --- Resolve PG connection from odoo.native.conf (port 1088 etc.) -------
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

# --- Ensure psql.exe + pg_restore.exe are callable -----------------------
# A recovery host often does NOT have PostgreSQL's bin\ on PATH (the installer
# does not add it). Auto-detect it (service / registry / standard install dirs,
# newest version first) and prepend it to PATH so the bare psql/pg_restore calls
# below resolve. Fail up front with a clear message rather than a cryptic
# "term not recognized" mid-restore. No version is hard-coded.
. (Join-Path $PSScriptRoot 'pg-bin-lib.ps1')
try { $null = Use-PgBin }
catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }

if (-not (Test-Path $BackupFile)) {
    Write-Host "Backup not found: $BackupFile" -ForegroundColor Red
    exit 1
}

# --- Resolve passphrase --------------------------------------------------
# Keep the passphrase as a [SecureString] in this script's variable space
# (matches backup-native.ps1 / restore-drill.ps1); it is converted to
# plaintext only at the gpg stdin boundary inside Start-GpgDecrypt.
if (-not $Passphrase) {
    if (Test-Path $EnvPath) {
        $line = (Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1)
        if ($line) {
            $envPass = $line.Matches.Groups[1].Value.Trim()
            if ($envPass) { $Passphrase = ConvertTo-SecureString $envPass -AsPlainText -Force }
            $envPass = $null   # wipe the plaintext local immediately
        }
    }
}
if (-not $Passphrase) {
    $Passphrase = Read-Host "Enter BACKUP_PASSPHRASE" -AsSecureString
}

# --- Find gpg.exe --------------------------------------------------------
$gpgCmd = Get-Command gpg.exe -ErrorAction SilentlyContinue
$gpg = if ($gpgCmd) { $gpgCmd.Source } else { $null }
if (-not $gpg) {
    foreach ($cand in @(
        'C:\Program Files (x86)\GnuPG\bin\gpg.exe',
        'C:\Program Files\GnuPG\bin\gpg.exe'
    )) { if (Test-Path $cand) { $gpg = $cand; break } }
}
if (-not $gpg) { Write-Host "gpg.exe not found." -ForegroundColor Red; exit 1 }

function Start-GpgDecrypt {
    param(
        [Parameter(Mandatory)] [SecureString]$Pass,
        [Parameter(Mandatory)] [string]$InputFile,
        [Parameter(Mandatory)] [string]$OutputFile
    )
    # Convert to plaintext ONLY here, in a short-lived local, and pipe it to
    # gpg's stdin via cmd's `echo|` (mirrors backup-native.ps1's Start-GpgPipe).
    # Capture stderr; only print it if gpg actually failed (gpg-agent logs
    # aren't errors).
    # FPAT High: passphrases containing cmd.exe metacharacters (& | < > ^ %)
    # were silently truncated by the previous `cmd /c echo|gpg` invocation,
    # making the encrypted backup unrecoverable. Use a passphrase FILE so
    # the shell never sees the passphrase.
    $errFile = [System.IO.Path]::GetTempFileName()
    $pwFile = [System.IO.Path]::GetTempFileName()
    $plain = $null
    try {
        $plain = [System.Net.NetworkCredential]::new('', $Pass).Password
        [System.IO.File]::WriteAllBytes(
            $pwFile, [System.Text.Encoding]::UTF8.GetBytes($plain)
        )
        # Closure-sprint: invoke via cmd /c so PowerShell never sees the
        # gpg-agent start-up text on stderr (PS 5.1 wraps that as a fatal
        # NativeCommandError under $ErrorActionPreference='Stop'). Same fix
        # as backup-native.ps1; passphrase-file safety is preserved.
        $cmd = '"' + $gpg + '" --batch --yes --pinentry-mode loopback ' +
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
        $plain = $null   # wipe the plaintext local
        if (Test-Path -LiteralPath $pwFile) {
            try { [System.IO.File]::WriteAllBytes($pwFile, (New-Object byte[] 64)) } catch {}
            Remove-Item -LiteralPath $pwFile -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
}

# --- 1. Decrypt the DB dump ---------------------------------------------
$tmpDump = [System.IO.Path]::GetTempFileName() + '.dump'
Write-Host "Decrypting $BackupFile" -ForegroundColor Cyan
Start-GpgDecrypt -Pass $Passphrase -InputFile $BackupFile -OutputFile $tmpDump
Write-Host "    OK ($((Get-Item $tmpDump).Length) bytes plaintext)" -ForegroundColor Green

try {
    # --- 2. Check target DB existence --------------------------------------
    $exists = & psql -U $DbUser -h $DbHost -p $DbPort -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DbName';" 2>$null
    if ($exists -and -not $Force) {
        Write-Host "Database '$DbName' already exists. Pass -Force to drop + restore." -ForegroundColor Red
        exit 1
    }
    if ($exists) {
        Write-Host "Dropping existing database '$DbName' (-Force given)" -ForegroundColor Yellow
        # Fail LOUD, not silent. A native exe's nonzero exit is NOT turned into a
        # terminating error by $ErrorActionPreference='Stop', so we must add
        # ON_ERROR_STOP + an explicit $LASTEXITCODE check (the pg_restore call
        # below already does this). WITH (FORCE) terminates other sessions (PG13+)
        # so an up Odoo service cannot block the drop and leave the restore to
        # layer onto a live database.
        & psql -U $DbUser -h $DbHost -p $DbPort -d postgres -w -v ON_ERROR_STOP=1 `
            -c "DROP DATABASE IF EXISTS $DbName WITH (FORCE);"
        if ($LASTEXITCODE -ne 0) { throw "DROP DATABASE $DbName failed (exit $LASTEXITCODE)." }
    }
    Write-Host "Creating database '$DbName'" -ForegroundColor Cyan
    & psql -U $DbUser -h $DbHost -p $DbPort -d postgres -w -v ON_ERROR_STOP=1 `
        -c "CREATE DATABASE $DbName OWNER odoo;"
    if ($LASTEXITCODE -ne 0) { throw "CREATE DATABASE $DbName failed (exit $LASTEXITCODE)." }

    # --- 3. pg_restore -----------------------------------------------------
    Write-Host "Restoring dump into '$DbName'" -ForegroundColor Cyan
    & pg_restore -U $DbUser -h $DbHost -p $DbPort -d $DbName --no-owner --no-acl $tmpDump
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed (exit $LASTEXITCODE)"
    }
    Write-Host "    Database restored" -ForegroundColor Green

    # --- 4. Filestore (if sibling .zip.gpg exists) -------------------------
    $zipEnc = $BackupFile -replace '\.dump\.gpg$', '-filestore.zip.gpg'
    if (Test-Path $zipEnc) {
        $tmpZip = [System.IO.Path]::GetTempFileName() + '.zip'
        Write-Host "Decrypting filestore $zipEnc" -ForegroundColor Cyan
        Start-GpgDecrypt -Pass $Passphrase -InputFile $zipEnc -OutputFile $tmpZip
        $target = Join-Path $DataDir "filestore"
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Write-Host "Extracting filestore -> $target" -ForegroundColor Cyan
        Expand-Archive -Path $tmpZip -DestinationPath $target -Force
        Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
        Write-Host "    Filestore extracted" -ForegroundColor Green
    } else {
        Write-Host "    [info] No matching filestore.zip.gpg; skipped" -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Restore complete. Start Odoo with scripts\start-native.ps1." -ForegroundColor Green
} finally {
    Remove-Item $tmpDump -Force -ErrorAction SilentlyContinue
}

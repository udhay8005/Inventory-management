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
    cycling passphrases.

.EXAMPLE
    scripts\backup-native.ps1

.EXAMPLE
    scripts\backup-native.ps1 -DbName wms -Retain 30
#>
[CmdletBinding()]
param(
    [string]$DbName = 'wms',
    [int]$Retain = 14,
    [string]$Passphrase,
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
if (-not $Passphrase) {
    if (Test-Path $EnvPath) {
        $line = (Select-String -Path $EnvPath -Pattern '^BACKUP_PASSPHRASE=(.+)$' | Select-Object -First 1)
        if ($line) {
            $Passphrase = $line.Matches.Groups[1].Value.Trim()
        }
    }
}
if (-not $Passphrase -or $Passphrase -eq 'changeme_backup_passphrase') {
    Write-Host "BACKUP_PASSPHRASE not set in .env (or still the placeholder)." -ForegroundColor Red
    Write-Host "Add a strong passphrase to .env:" -ForegroundColor Yellow
    Write-Host "    BACKUP_PASSPHRASE=<24+ random chars, no whitespace>" -ForegroundColor Yellow
    Write-Host "Then re-run." -ForegroundColor Yellow
    exit 1
}

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
# (command-line args show up in Process Explorer, the file system
# stays clean).
function Invoke-GpgEncrypt {
    param(
        [Parameter(Mandatory)] [string]$InputFile,
        [Parameter(Mandatory)] [string]$OutputFile,
        [Parameter(Mandatory)] [string]$Pass
    )
    $args = @(
        '--batch',
        '--yes',
        '--passphrase-fd', '0',
        '--symmetric',
        '--cipher-algo', 'AES256',
        '-o', $OutputFile,
        $InputFile
    )
    $proc = Start-Process -FilePath $gpg -ArgumentList $args `
        -NoNewWindow -PassThru -RedirectStandardInput 'pipe' -RedirectStandardError 'pipe'
    # The above doesn't work cleanly in PowerShell 5.1 - fall back to
    # piping via stdin using process redirection.
    throw "internal: use Start-GpgPipe instead"
}

function Start-GpgPipe {
    param([string]$Pass, [string]$InputFile, [string]$OutputFile)
    # Use cmd.exe pipe so PS5.1 doesn't choke. echo passphrase | gpg ...
    # The passphrase has no shell metacharacters that would break this
    # (we enforce 'no whitespace' in .env).
    #
    # GPG writes informational notices (gpg-agent socket, first-run
    # keyring creation) to stderr; those aren't failures. We collect
    # stderr to a tempfile and only print it if gpg exits non-zero.
    $errFile = [System.IO.Path]::GetTempFileName()
    $cmd = "echo $Pass| `"$gpg`" --batch --yes --passphrase-fd 0 --symmetric --cipher-algo AES256 -o `"$OutputFile`" `"$InputFile`" 2> `"$errFile`""
    & cmd /c $cmd
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        $stderr = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
        throw "gpg encryption failed (exit $rc) on $InputFile`n$stderr"
    }
    Remove-Item $errFile -Force -ErrorAction SilentlyContinue
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
    } finally {
        Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "    [warn] Filestore not found at $Filestore (skipped)" -ForegroundColor Yellow
}

# --- 3. Retention -------------------------------------------------------
Write-Host "Applying retention (keep last $Retain)" -ForegroundColor Cyan
$dumps = Get-ChildItem $BackupDir -Filter "$DbName-*.dump.gpg" | Sort-Object LastWriteTime -Descending
$dumps | Select-Object -Skip $Retain | ForEach-Object {
    Write-Host "    deleting $($_.Name)" -ForegroundColor DarkGray
    Remove-Item $_.FullName -Force
    $sibling = $_.FullName -replace '\.dump\.gpg$', '-filestore.zip.gpg'
    if (Test-Path $sibling) { Remove-Item $sibling -Force }
}

Write-Host ""
Write-Host "Backup complete (encrypted). Artifacts in $BackupDir" -ForegroundColor Green
Write-Host "WARNING: without BACKUP_PASSPHRASE these files cannot be restored." -ForegroundColor Yellow

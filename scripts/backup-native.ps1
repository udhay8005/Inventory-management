<#
.SYNOPSIS
    Back up the native WMS — Postgres dump + filestore zip.

.DESCRIPTION
    Writes two timestamped artifacts to .\backups\:
        wms-<timestamp>.sql.gz       - pg_dump in custom format, gzipped
        wms-<timestamp>-filestore.zip - the data_dir\filestore\wms tree

    Keeps the most recent N backups (-Retain, default 14).

.PARAMETER DbName
    Database to dump. Default: wms.

.PARAMETER Retain
    Number of most-recent backups to keep. Default: 14.

.EXAMPLE
    scripts\backup-native.ps1

.EXAMPLE
    scripts\backup-native.ps1 -DbName wms -Retain 30
#>
[CmdletBinding()]
param(
    [string]$DbName = 'wms',
    [int]$Retain = 14
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir   = Join-Path $ProjectRoot 'backups'
$DataDir     = Join-Path $ProjectRoot '.runtime\data'
$Stamp       = Get-Date -Format 'yyyyMMdd-HHmmss'

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# ─── 1. Database dump ─────────────────────────────────────────────────────
$DumpPath = Join-Path $BackupDir "$DbName-$Stamp.dump"
Write-Host "Dumping database '$DbName' -> $DumpPath" -ForegroundColor Cyan
& pg_dump -U odoo -h localhost -d $DbName -Fc -f $DumpPath
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed. Set `$env:PGPASSWORD if Postgres needs a password."
}
Write-Host "    Database dumped" -ForegroundColor Green

# ─── 2. Filestore zip ─────────────────────────────────────────────────────
$Filestore = Join-Path $DataDir "filestore\$DbName"
if (Test-Path $Filestore) {
    $ZipPath = Join-Path $BackupDir "$DbName-$Stamp-filestore.zip"
    Write-Host "Zipping filestore -> $ZipPath" -ForegroundColor Cyan
    Compress-Archive -Path $Filestore -DestinationPath $ZipPath -Force
    Write-Host "    Filestore archived" -ForegroundColor Green
} else {
    Write-Host "    [warn] Filestore not found at $Filestore (skipped)" -ForegroundColor Yellow
}

# ─── 3. Retention ─────────────────────────────────────────────────────────
Write-Host "Applying retention (keep last $Retain)" -ForegroundColor Cyan
$dumps = Get-ChildItem $BackupDir -Filter "$DbName-*.dump" | Sort-Object LastWriteTime -Descending
$dumps | Select-Object -Skip $Retain | ForEach-Object {
    Write-Host "    deleting $($_.Name)" -ForegroundColor DarkGray
    Remove-Item $_.FullName -Force
    $sibling = $_.FullName -replace '\.dump$', '-filestore.zip'
    if (Test-Path $sibling) { Remove-Item $sibling -Force }
}

Write-Host "`nBackup complete. Artifacts in $BackupDir" -ForegroundColor Green

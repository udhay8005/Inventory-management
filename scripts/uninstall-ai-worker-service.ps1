#Requires -Version 5.1
<#
.SYNOPSIS
    Remove the supervised AI forecast worker service created by
    install-ai-worker-service.ps1. Self-elevating.

.EXAMPLE
    .\scripts\uninstall-ai-worker-service.ps1
#>
[CmdletBinding()]
param([string]$ServiceName = 'Odoo-WMS-AIWorker')
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Administrator rights required - relaunching elevated (approve the UAC prompt)..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath), '-ServiceName', $ServiceName
    )
    return
}

function Resolve-Nssm {
    $c = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($g in @(
            "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM*\*\win64\nssm.exe",
            'C:\Program Files\nssm*\win64\nssm.exe',
            'C:\ProgramData\chocolatey\bin\nssm.exe')) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

if (-not (Get-Service $ServiceName -ErrorAction SilentlyContinue)) {
    Write-Host "'$ServiceName' not found - nothing to do." -ForegroundColor Yellow
    return
}
$nssm = Resolve-Nssm
if ($nssm) {
    & $nssm stop $ServiceName confirm 2>$null | Out-Null
    & $nssm remove $ServiceName confirm | Out-Null
} else {
    & sc.exe stop $ServiceName | Out-Null
    & sc.exe delete $ServiceName | Out-Null
}
Write-Host "Removed '$ServiceName'." -ForegroundColor Green

<#
.SYNOPSIS
    Start a Cloudflare tunnel exposing the local WMS over HTTPS.

.DESCRIPTION
    Native replacement for the cloudflared_quick / cloudflared_named
    docker-compose profiles. Wraps the cloudflared.exe binary so phones
    and remote browsers can reach the WMS over the internet without
    opening router ports.

    Two modes (pick one via -Mode):

      -Mode Quick   Random *.trycloudflare.com URL, no account needed.
                    Good for demos. URL changes each restart and is
                    printed to the console.

      -Mode Named   Permanent URL on your own Cloudflare-managed domain
                    (e.g. wms.example.org). Requires a free Cloudflare
                    account, a created tunnel, and the tunnel TOKEN set
                    in .env as CLOUDFLARE_TUNNEL_TOKEN.

    If cloudflared.exe isn't installed yet, the script will offer to
    install it via winget (elevation required for system-wide install).

.PARAMETER Mode
    'Quick' (default) or 'Named'.

.PARAMETER Token
    Override the tunnel token (otherwise read from .env).

.PARAMETER Port
    Local Odoo port to tunnel to. Default: 8069.

.EXAMPLE
    scripts\start-tunnel.ps1
    # Quick tunnel - prints the trycloudflare.com URL

.EXAMPLE
    scripts\start-tunnel.ps1 -Mode Named
    # Persistent tunnel using the token in .env

.NOTES
    Cloudflare tunnels are free for personal / small-team use. See
    https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
#>
[CmdletBinding()]
param(
    [ValidateSet('Quick','Named')]
    [string]$Mode = 'Quick',
    [string]$Token,
    [int]$Port = 8069
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot '.env'

# ---- Ensure cloudflared is installed -------------------------------------
$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "cloudflared.exe is not installed." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing via winget (will prompt for elevation)..." -ForegroundColor Cyan
        Start-Process winget -Verb RunAs -Wait -ArgumentList @(
            'install','--id','Cloudflare.cloudflared','--silent',
            '--accept-package-agreements','--accept-source-agreements'
        )
        # Refresh PATH for this session
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                    [System.Environment]::GetEnvironmentVariable('Path','User')
        $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    }
    if (-not $cf) {
        Write-Host "Install manually from https://github.com/cloudflare/cloudflared/releases" -ForegroundColor Red
        exit 1
    }
}
Write-Host "cloudflared: $($cf.Source)" -ForegroundColor Gray

# ---- Verify Odoo is up before tunneling ----------------------------------
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port/web/login" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "Odoo responding on localhost:$Port (HTTP $($r.StatusCode))" -ForegroundColor Gray
} catch {
    Write-Host "WARNING: nothing answering on localhost:$Port" -ForegroundColor Yellow
    Write-Host "  Start Odoo first: scripts\start-native.ps1" -ForegroundColor Yellow
    Write-Host "  Continuing anyway - tunnel will fail until Odoo comes up." -ForegroundColor Yellow
}

# ---- Start the tunnel -----------------------------------------------------
if ($Mode -eq 'Quick') {
    Write-Host ""
    Write-Host "Starting QUICK tunnel (random *.trycloudflare.com URL)" -ForegroundColor Cyan
    Write-Host "Look for the assigned URL in the output below." -ForegroundColor DarkGray
    Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
    Write-Host ""
    & cloudflared tunnel --no-autoupdate --url "http://localhost:$Port"
}
else {
    # Resolve token: CLI > parent env > .env file
    if (-not $Token) {
        $Token = $env:CLOUDFLARE_TUNNEL_TOKEN
    }
    if (-not $Token -and (Test-Path $EnvFile)) {
        $line = Select-String -Path $EnvFile -Pattern '^\s*CLOUDFLARE_TUNNEL_TOKEN\s*=\s*(.+?)\s*$' | Select-Object -First 1
        if ($line) { $Token = $line.Matches.Groups[1].Value.Trim() }
    }
    if (-not $Token) {
        Write-Host "No tunnel token found." -ForegroundColor Red
        Write-Host "Create a tunnel at https://one.dash.cloudflare.com -> Networks -> Tunnels" -ForegroundColor Yellow
        Write-Host "Then add to .env:    CLOUDFLARE_TUNNEL_TOKEN=eyJh...." -ForegroundColor Yellow
        exit 1
    }
    Write-Host ""
    Write-Host "Starting NAMED tunnel" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
    Write-Host ""
    & cloudflared tunnel --no-autoupdate run --token $Token
}

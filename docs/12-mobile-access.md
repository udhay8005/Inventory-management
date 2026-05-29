# 12 — Mobile access (LAN + permanent HTTPS tunnel)

Three independent ways to reach the WMS from a phone. Pick whichever fits.

| Method | URL example | Works on mobile data? | Stable? | Setup time |
|---|---|---|---|---|
| WiFi (same network) | `http://192.168.1.50:8169` | ❌ WiFi only | as long as your IP stays | 2 min |
| Cloudflare quick tunnel | `https://abc-xyz-def.trycloudflare.com` | ✅ | URL changes per restart | 1 min |
| Cloudflare named tunnel | `https://wms.your-domain.com` | ✅ | permanent | 10 min |

The scan-issue camera capture works in all three — modern browsers expose the
device camera over plain HTTP **on localhost** and over HTTPS everywhere else.
So WiFi access needs `https://…` for the camera to open; the tunnel options
both give you HTTPS for free.

## A. WiFi (same network)

### 1. Find the host PC's IP

```powershell
ipconfig | Select-String -Pattern "IPv4"
```

Look for an address like `192.168.x.x` or `10.0.x.x` — that's the LAN IP.

### 2. Open the port in Windows Firewall

```powershell
New-NetFirewallRule -DisplayName "WMS Odoo 8169" -Direction Inbound `
    -LocalPort 8169 -Protocol TCP -Action Allow
```

### 3. Visit from the phone

```
http://<host-IP>:8169
```

Note: the camera widget will refuse to open over plain HTTP on a non-localhost
URL because modern browsers block `MediaDevices.getUserMedia` outside secure
contexts. Use the tunnel options below for camera support over LAN, or accept
that operators have to upload an existing photo file instead of taking one
live.

## B. Cloudflare quick tunnel (random URL, no account)

```powershell
scripts\start-tunnel.ps1
```

The first run will offer to install `cloudflared.exe` via winget if it's
not already on the system (one-time admin elevation). Subsequent runs
just start the tunnel.

You'll see a line like:

```
2026-05-14T... INF +--------------------------------------------------------+
2026-05-14T... INF |  Your quick Tunnel has been created!                   |
2026-05-14T... INF |  Visit it at:                                          |
2026-05-14T... INF |  https://chicken-banana-purple.trycloudflare.com       |
2026-05-14T... INF +--------------------------------------------------------+
```

That URL serves the WMS over HTTPS from anywhere — your phone on cellular,
a partner across town, anywhere. The URL is regenerated every time
`start-tunnel.ps1` is run.

To stop: press Ctrl+C in the tunnel window.

## C. Cloudflare named tunnel (permanent URL)

### 1. Create a free Cloudflare account
<https://dash.cloudflare.com/sign-up>

### 2. Create a tunnel and grab the token

- Go to <https://one.dash.cloudflare.com>
- **Networks → Tunnels → Create a tunnel** → name it `wms`.
- After saving you'll see a token starting with `eyJ...`. Copy it.
- Add a public hostname like `wms.your-domain.com` pointing to
  `http://localhost:8069` (the WMS port on the host running the tunnel).
- (If you don't own a domain, buy `.app` / `.dev` etc. on Cloudflare for ~$10/yr.)

### 3. Paste the token into `.env`

```
CLOUDFLARE_TUNNEL_TOKEN=eyJh...long_string...
```

### 4. Start the named tunnel

```powershell
scripts\start-tunnel.ps1 -Mode Named
```

Visit `https://wms.your-domain.com` from anywhere. It will work on mobile
data, the camera will open, and the URL never changes.

For production, register the tunnel as a Windows service so it auto-starts
on boot. Either via NSSM (see docs/07-deployment.md) or via cloudflared's
built-in installer: `cloudflared.exe service install <token>`.

## D. Add basic auth on the tunnel (optional but recommended)

If the tunnel exposes the WMS to the public internet, layer **Cloudflare
Access** policies in front:

- One Cloudflare Access policy that allows only your team's emails / Google
  Workspace / GitHub identities.
- Cloudflare handles the SSO flow before any request reaches Odoo.

Configure under **Cloudflare Zero Trust → Access → Applications → Add
application → Self-hosted → wms.your-domain.com**. No Odoo changes needed.

## Camera capture in the scan-issue wizard

When the wizard detects a non-unit product (Liters / KG / m³ / etc.) the
*Item photo* field becomes required and on mobile renders as a single
"Take photo" button. The OS camera opens, you shoot, the picker closes
itself, the field shows the thumbnail, and Validate commits everything
(picking + photo attached to the chatter).

For unit products you can still attach a photo if you want — useful for
proof-of-handover or damage documentation.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Phone can't reach `http://192.168.x.x:8169` | Windows firewall blocking | Run the firewall command in section A.2 |
| Camera doesn't open | Browser blocks getUserMedia over HTTP | Use a Cloudflare tunnel (HTTPS) |
| Quick tunnel URL keeps changing | That's by design | Switch to a named tunnel |
| Login page loads but actions fail | Wrong host IP / mixed http/https | Always pick one URL per session |
| 502 from Cloudflare | Odoo not running | `scripts\start-native.ps1` then retry tunnel |

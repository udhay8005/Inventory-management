# Inventory_mngt — Odoo CE 19 WMS

Production-ready Warehouse Management System on Odoo 19 Community Edition,
purpose-built for an internal-stock trust (no sales, no invoices, no money).
Runs **natively on Windows** — no Docker required.

**What's in the box:**

- 🏗 **Visual rack builder** — Rack → Compartment → Slot, plus open Floor Zones, with a per-rack flexible grid (4-way D-pad merging)
- 📦 **Scan-driven workflows** — Scan Receipt / Scan Return / Scan Issue (FIFO across slots) / Scan-Validate
- 🧾 **Audit trail invariant** — every stock-moving action records `wms_taken_by` / `wms_ordered_by` / `wms_storekeeper_id` on the resulting `stock.picking` plus a chatter message
- 👥 **Two-role security** — WMS Manager (Admin) vs WMS Store Keeper, with an admin-maintained roster of human keepers
- 🔧 **Damage / Repair workflow** — smart recommendation engine (urgent buy / repair / note only) + one-click Create Repair Order, full state machine (draft → in_repair → done / scrapped / cancelled) with chatter audit on every transition
- 🏷 **Thermal labels** — customisable 4×2 inch die-cut layout (logo / title / SKU / barcode), inline barcode, printer gap-sensor aware
- 🔁 **Returnability classification** — product Kind (Raw / Packaging / Fluid / Finished Good / WIP / Consumable / Tool / Spare) drives whether Scan Return accepts it
- 📈 **Buying recommendations** — daily-average usage + 7-day buffer for non-returnables; concurrent-users heuristic for tools/spares
- 📊 **Reports** — Where-is-it / Warehouse map / Oldest stock (FIFO) / Slot occupancy / Cycle count due / Movement history / Low stock alerts / Dead stock / Reorder summary
- 🤖 **Offline AI demand forecasting** — statsmodels-based, runs locally, no external API

## Quickstart (Windows)

One-shot installer — installs PostgreSQL 16, Python 3.12, wkhtmltopdf, Git
via `winget`, clones Odoo 19 source, sets up a Python venv, and initialises
the database. Takes ~10 minutes the first time.

```powershell
# From an Administrator PowerShell:
git clone https://github.com/udhay8005/Inventory-management.git
cd Inventory-management
copy .env.example .env       # edit and change DB_PASSWORD
scripts\install-native.ps1
```

Then start the server:

```powershell
scripts\start-native.ps1
```

Open <http://localhost:8069>. Sign in as `admin` / `admin` (change the password
immediately under your user profile). In **Apps** install in this order:

1. `wms_location` — racks, slots, floor zones, role groups
2. `wms_fifo` — FIFO removal across slots
3. `wms_barcode` — scan wizards, barcode aliases, storekeeper roster, thermal labels
4. `wms_repair_damage` — damage / repair / return workflows
5. `wms_ai_forecast` — offline statsmodels forecasting + reorder
6. `wms_reports` — SQL-view dashboards
7. `wms_training` — Help Center, guided tours, visual academy, SOPs

## Initial user setup

The `admin` user is added to **WMS / Manager** on first install. To onboard
a Store Keeper:

1. **WMS → Configuration → Store Keepers** — add the human names that will appear in audit forms (Ramesh, Lakshmi, Suresh, etc.). The roster is what keepers pick from at scan time; it's not Odoo accounts.
2. **Settings → Users & Companies → Users → Create** — make ONE shared Odoo login per shift (e.g. `storekeeper`) and assign role **WMS / Store Keeper**.
3. The keeper signs in, picks their name from the on-duty roster in every wizard; the picking records who-physically-did-it (audit) + who-the-Odoo-account-is (login).

## Roles at a glance

| Action | Manager (Admin) | Store Keeper |
|---|---|---|
| Add / edit / delete racks, slots, floor zones, products | ✅ | ❌ |
| Maintain the Store Keeper roster | ✅ | ❌ (view only) |
| Configure thermal label layout | ✅ | ❌ |
| Scan Receipt / Scan Return / Scan Issue | ✅ | ✅ |
| File a Damage event | ✅ | ✅ |
| Create Repair Order from a damage | ✅ | ✅ |
| Start / Mark Done / Scrap / Cancel a repair | ✅ | ❌ (view only) |
| View all reports | ✅ | ✅ |
| Browse raw Odoo Inventory app | ✅ | ❌ (hidden — WMS workflows are the only path) |

## Audit-trail invariant

Every action that moves stock records the audit triplet:

- **Reported by / Taken by / Delivered by** — the human who physically handled the goods
- **Authorised by / Ordered by** — who approved the move
- **Store Keeper on duty** — who was running the desk (picked from the roster)

These fields are mirrored onto the resulting `stock.picking` plus a chatter
message, so reports keyed off `stock.picking` read damage / repair / receipt
moves the same way. The damage and repair workflows **refuse to leave draft**
when any of the three fields is blank.

## Day-to-day commands

```powershell
# Core server lifecycle
scripts\start-native.ps1                       # Start the server
scripts\start-native.ps1 -Upgrade wms_barcode  # Restart upgrading a module
scripts\start-native.ps1 -Dev "reload,qweb"    # Dev mode (auto-reload)
scripts\stop-native.ps1                        # Graceful stop

# Run as an auto-starting Windows service (recommended for production)
scripts\install-odoo-service.ps1               # Create Odoo-WMS service (UAC) — auto-start + restart-on-failure
scripts\uninstall-odoo-service.ps1             # Remove the service
scripts\set-user-passwords.ps1 -Users "admin,storekeeper"  # Set strong unique passwords (printed once)

# Backup + recovery
scripts\backup-native.ps1                      # Dump DB + zip filestore
scripts\reset-pg-password.ps1                  # Forgot postgres password? Run this (UAC).

# Optional add-ons (run in a separate PowerShell window)
scripts\start-ai-worker.ps1                    # Out-of-process forecast worker
scripts\start-tunnel.ps1                       # Quick Cloudflare HTTPS tunnel
scripts\start-tunnel.ps1 -Mode Named           # Permanent tunnel (needs CLOUDFLARE_TUNNEL_TOKEN in .env)
```

PostgreSQL runs as a Windows service (`postgresql-x64-15/16/17` — auto-detected)
and auto-starts on boot, so the database is always there waiting.

## Project layout

```
Inventory_mngt/
├── .odoo/                      Odoo 19 source clone (created by install-native.ps1)
├── .venv/                      Python venv with all deps (ditto)
├── .runtime/                   data_dir + logs (ditto)
├── config/odoo.native.conf     Native Odoo config (generated by install-native.ps1)
├── requirements.txt            Project Python extras (statsmodels, pandas, reportlab, ...)
├── scripts/
│   ├── install-native.ps1      One-shot installer
│   ├── start-native.ps1        Start Odoo
│   ├── stop-native.ps1         Stop Odoo
│   └── backup-native.ps1       Dump + zip
├── ai_worker/                  Optional out-of-process forecast runner (statsmodels)
│                               Run natively via scripts\start-ai-worker.ps1
├── docs/                       Architecture & design notes
└── addons/
    ├── wms_location/           Rack/Compartment/Slot model + role groups + rack builder OWL component
    ├── wms_fifo/               FIFO removal across slots + partial index
    ├── wms_barcode/            scan wizards + barcode aliases + storekeeper roster + label printing
    ├── wms_repair_damage/      damage / repair / return flows + recommendation engine
    ├── wms_ai_forecast/        offline statsmodels forecasting + reorder
    ├── wms_reports/            SQL-view dashboards (Where-is-it, FIFO age, occupancy, ...)
    └── wms_training/           Help Center, guided tours, visual academy, SOPs
```

## Read the docs

Architecture, design notes, and operational guides:

- [`docs/01-architecture.md`](docs/01-architecture.md) — stack & layering
- [`docs/02-data-model.md`](docs/02-data-model.md) — why we extend `stock.location`
- [`docs/03-workflows.md`](docs/03-workflows.md) — inbound / outbound / repair flows
- [`docs/04-barcode-flow.md`](docs/04-barcode-flow.md) — scanner integration + carton aliases
- [`docs/05-ai-prediction.md`](docs/05-ai-prediction.md) — algorithm choice + offline footprint
- [`docs/06-reports.md`](docs/06-reports.md) — every dashboard, what it shows, how
- [`docs/07-deployment.md`](docs/07-deployment.md) — production deploy + restore
- [`docs/08-security.md`](docs/08-security.md) — role model, ACLs, record rules
- [`docs/09-roadmap.md`](docs/09-roadmap.md) — phased build plan
- [`docs/10-testing.md`](docs/10-testing.md) — test strategy
- [`docs/11-maintenance.md`](docs/11-maintenance.md) — upgrades, tuning, FAQ
- [`docs/12-mobile-access.md`](docs/12-mobile-access.md) — phones / tablets / off-site
- [`docs/13-operations-playbook.md`](docs/13-operations-playbook.md) — daily / weekly / monthly ops
- [`docs/14-sku-naming.md`](docs/14-sku-naming.md) — product code conventions
- [`docs/15-onboarding-script.md`](docs/15-onboarding-script.md) — first-day Store Keeper training
- [`docs/16-hardware-guide.md`](docs/16-hardware-guide.md) — scanners + thermal printers
- [`docs/17-ci-cd.md`](docs/17-ci-cd.md) — GitHub Actions pipeline + release flow
- [`docs/20-end-to-end-flow.md`](docs/20-end-to-end-flow.md) — full lifecycle ASCII diagram
- [`docs/PRODUCTION-READINESS.md`](docs/PRODUCTION-READINESS.md) — production sign-off checklist
- [`docs/RUN-AS-SERVICE.md`](docs/RUN-AS-SERVICE.md) — run Odoo as an auto-starting Windows service
- [`docs/LABEL-PRINTING.md`](docs/LABEL-PRINTING.md) — thermal 4×2 labels + printer gap calibration

## Mobile access (phones / tablets / off-site)

The simplest local path:

```powershell
# Right-click PowerShell → Run as Administrator, then:
New-NetFirewallRule -DisplayName "WMS Odoo" -Direction Inbound -LocalPort 8069 -Protocol TCP -Action Allow
```

…then phones on the same WiFi can open `http://<host-IP>:8069`. For
permanent HTTPS over the internet, run a Cloudflare named tunnel via
`cloudflared.exe` — see [docs/12-mobile-access.md](docs/12-mobile-access.md).

The scan wizards are mobile-responsive and open the device camera for the
optional item photo (required for liquid / weight / volume items).

## Hardware

USB / Bluetooth HID barcode scanners "just work" — they keyboard-type into the
focused field on the scan wizards. Any thermal printer your **host OS** can see
will print the generated PDF labels. Tested with 4×2 inch die-cut direct-thermal
stock on a TSC TE244 (gap-sensor); layout is admin-configurable so other label
sizes work too. See [docs/LABEL-PRINTING.md](docs/LABEL-PRINTING.md).

## Run tests

```powershell
.venv\Scripts\activate
python .odoo\odoo-bin -c config\odoo.native.conf -d wms_test --test-enable --stop-after-init `
    -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports `
    --without-demo=all --test-tags wms
```

## Backup / restore

```powershell
scripts\backup-native.ps1            # Writes .\backups\wms-<timestamp>.dump.gpg + filestore zip

# Restore — see docs/07-deployment.md
scripts/restore-native.ps1 -BackupPath backups/wms-<timestamp>.dump.gpg
```

A weekly restore drill (`scripts/restore-drill.ps1`) verifies the most recent encrypted backup is still recoverable - the drill never touches the production database. See `docs/18-restore-drill.md` for the runbook.

## CI / CD

GitHub Actions pipeline (Ubuntu runner — installs PostgreSQL + Python + Odoo
source natively, mirroring the local Windows setup). See [docs/17-ci-cd.md](docs/17-ci-cd.md).

```powershell
make lint            # black, isort, flake8, xml well-formedness (needs make + WSL or Git Bash)
make test            # full Odoo test suite (slow)
make format          # auto-fix style
```

Or use the underlying tools directly:

```powershell
.venv\Scripts\activate
black --check addons\ scripts\ ai_worker\
isort --check-only addons\ scripts\ ai_worker\
flake8 addons\
```

## Release workflow

Branch protection on `main` requires a pull request. Workflow:

1. Feature work lands on `test` → CI runs on every push
2. When `test` is green, open a PR `test → main`
3. After merge, the `Release` workflow auto-tags the highest version found
   across all `addons/*/__manifest__.py` and publishes a GitHub Release with
   a changelog generated from `last_tag..HEAD --no-merges`

To cut a new release: bump the version on whichever module changed (the
highest version across all manifests becomes the project version).

## License

LGPL-3 (matches Odoo CE).

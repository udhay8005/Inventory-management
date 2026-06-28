# Inventory_mngt — Odoo CE 19 WMS

[![CI](https://github.com/udhay8005/Inventory-management/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/udhay8005/Inventory-management/actions/workflows/ci.yml)
[![CI (v20)](https://github.com/udhay8005/Inventory-management/actions/workflows/ci.yml/badge.svg?branch=v20)](https://github.com/udhay8005/Inventory-management/actions/workflows/ci.yml)
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Latest release](https://img.shields.io/github/v/release/udhay8005/Inventory-management?sort=semver)](https://github.com/udhay8005/Inventory-management/releases/latest)

Production-ready Warehouse Management System on Odoo 19 Community Edition,
purpose-built for an internal-stock trust (no sales, no invoices, no money).
Runs **natively on Windows** — no Docker required.

**What's in the box:**

- 🏗 **Visual rack builder** — Rack → Compartment → Slot, plus open Floor Zones, with a per-rack flexible grid (4-way D-pad merging)
- 📦 **Scan-driven workflows** — Scan Receipt / Scan Return / Scan Issue (FIFO across slots) / Scan-Validate
- 🧾 **Audit trail invariant** — every stock-moving action records `wms_taken_by` / `wms_ordered_by` / `wms_storekeeper_id` on the resulting `stock.picking` plus a chatter message
- 👥 **Tiered role security** — 3 base roles (Manager / Store Keeper / Repair Tech) + optional Buyer, layered with 5 capability sub-groups (scan-receive / scan-issue / file-damage / submit-audit / manage-catalog), plus an admin-maintained roster of human keepers
- 🔧 **Damage / Repair workflow** — smart recommendation engine (urgent buy / repair / note only) + one-click Create Repair Order, full state machine (draft → in_repair → done / scrapped / cancelled) with chatter audit on every transition
- 🏷 **Thermal labels** — customisable 4×1 inch (100×25 mm) die-cut layout (logo / title / SKU / barcode), inline barcode, printer gap-sensor aware
- 🔁 **Returnability classification** — product Kind (Raw / Packaging / Fluid / Finished Good / WIP / Consumable / Tool / Spare) drives whether Scan Return accepts it
- 📈 **Buying recommendations** — daily-average usage + 7-day buffer for non-returnables; concurrent-users heuristic for tools/spares
- 📊 **Reports** — Where-is-it / Warehouse map / Oldest stock (FIFO) / Slot occupancy / Cycle count due / Movement history / Low stock alerts / Dead stock / Reorder summary
- 🖥 **Executive Dashboard** at `/wms/dashboard` — one manager-only screen: health, stock totals, attention badges, today's activity
- 🔎 **Smart Find** at `/wms/find` — type a name / SKU / barcode → slot + qty, or tap a chip ("low stock", "expiring", "dead stock", "damaged", "under repair")
- 💰 **Cost / value reports** — Stock Value, Consumption Value (broken down by purpose: Cows / Pooja / Maintenance / …), Product Lifecycle, plus value-at-risk on Expiry / Damage / Dead Stock
- 🎯 **Issue dimensions** — every Scan Issue captures a configurable **Department** (Gaushala / Veterinary / Dairy / Fodder / …), an optional **Purpose** and **Animal/cow**, driving consumption-by-department pivots (the legacy *Issued for* tag is auto-derived for back-compat)
- 🔒 **Issue approvals** — a min-life re-request guard (same department, same product, too soon) and a configurable high-value threshold route an issue to a manager-only **Approvals** queue; the keeper types a reason but cannot self-approve, and approval re-checks stock before issuing
- ↩️ **Returnable items** — tools / spares can be marked returnable with an expected-return period; a daily alert + **Returns-due report** surface overdue items, and Scan Return clears them
- 🔔 **Alert hardening** — low-stock / expiry / backup-stale / restore-fail / health-CRITICAL alerts delivered to every WMS Manager's Discuss Inbox (via `message_notify`), with optional email via `wms_reports.alert_email`
- ↩️ **One-click Undo** within a configurable window (default 15 min) — compensating internal transfer, no deletes
- 🧪 **One-button Self-Diagnostics** — DB / backup-file / disk / duplicate-SKU / orphan-slot / negative-stock probes in one screen
- 📐 **Opt-in slot capacity enforcement** (`wms_location.enforce_capacity`)
- 🤖 **Offline AI demand forecasting** — statsmodels-based, runs locally, no external API
- 🛡️ **Off-site encrypted backup copy** — `BACKUP_OFFSITE_DIR` (USB, network share, OneDrive sync folder — all just paths), SHA-256 verified after copy
- ☁️ **Google Drive cloud backup** (optional) — every encrypted backup set uploaded to an `Inventory_Backups` Drive folder (`drive.file` minimal scope, `sha256Checksum`-verified, tiered retention), plus an in-app **Backup Now** button
- 🧬 **Universal Perishable Engine** (v20 — `wms_perishable`) — per-lot FEFO (earliest-expiry-first), expired-stock block + manager override + disposal carve-out, lot-aware receipt (batch / expiry / supplier capture), lot recall, quarantine, per-lot expiry report (180/90/60/30/15/7/expired bands), lot barcode labels + scan-back, near-expiry receiving guard, one-click lot timeline, and a stable extension hook API (v20 Hook API 1.0). Additive over v19 — no existing behaviour changes; install optionally after the v19 base modules

## Quickstart (Windows)

One-shot installer — installs PostgreSQL 15/16/17 (auto-detected; winget installs 17 by default), Python 3.12, wkhtmltopdf, Git
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
8. `wms_perishable` *(v20 — optional)* — Universal Perishable Engine: per-lot FEFO, expiry tracking, recall, quarantine, lot labels, near-expiry guard, extension hooks. Install this only on the `v20` branch (pilot stage); see [`docs/v20-perishable-engine/10-pilot-release-v20.0.0-beta1.md`](docs/v20-perishable-engine/10-pilot-release-v20.0.0-beta1.md)

## Initial user setup

The `admin` user is added to **WMS / Manager** on first install. To onboard
a Store Keeper:

1. **WMS → Configuration → Store Keepers** — add the human names that will appear in audit forms (Ramesh, Lakshmi, Suresh, etc.). The roster is what keepers pick from at scan time; it's not Odoo accounts.
2. **Settings → Users & Companies → Users → Create** — make ONE shared Odoo login per shift (e.g. `storekeeper`) and assign role **WMS / Store Keeper**.
3. The keeper signs in, picks their name from the on-duty roster in every wizard; the picking records who-physically-did-it (audit) + who-the-Odoo-account-is (login).

## Roles at a glance

Two-tier role model: pick a base role, then layer capability sub-groups on top
of Store Keeper as needed.

**Three base roles + an optional Buyer role:**

- **WMS / Manager** (`group_wms_manager`) — full admin: racks, slots, products, roster, label layout, repair lifecycle, all reports
- **WMS / Store Keeper** (`group_wms_user`) — runs the desk; capability sub-groups gate which scan / damage / audit / catalog wizards they can open
- **WMS / Repair Tech** (`group_repair_tech`) — handles in-repair items (start / mark done / scrap / cancel); no scan wizards, no catalog edits
- **WMS / Buyer** (`group_buyer`, optional) — reads reorder summary + buying recommendations; does not move stock

**Then layer capabilities (all sub-groups of Store Keeper, namespace `wms_location.*`):**

- `group_wms_can_scan_receive` — Scan Receipt / Scan Return
- `group_wms_can_scan_issue` — Scan Issue (FIFO across slots)
- `group_wms_can_file_damage` — file a Damage event, create Repair Order from it
- `group_wms_can_submit_audit` — submit cycle-count audits
- `group_wms_can_manage_catalog` — barcode aliases, storekeeper roster entries

Full role model + ACL detail in [08-security.md](docs/08-security.md).

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

PostgreSQL 15/16/17 (auto-detected; winget installs 17 by default) runs as a Windows
service (`postgresql-x64-15/16/17`) and auto-starts on boot, so the database is
always there waiting.

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
    ├── wms_training/           Help Center, guided tours, visual academy, SOPs
    ├── wms_perishable/         [v20 Wave 1] Universal Perishable Engine — per-lot FEFO, expiry, recall,
    │                           quarantine, lot labels, near-expiry guard, per-kind shelf-life, hook API
    ├── wms_analytics/          [v20 Wave 2] Warehouse Intelligence — KPI dashboard, expiry-risk engine,
    │                           supplier/disposal analytics, stock-health, ledgers, recall dashboard,
    │                           lot audit, heat map, cold chain, bulk ops, cycle-count, traceability
    └── wms_pharmacy/           [v20 Wave 3] Pharmacy packaging engine — Box→Strip→Tablet, nested
                                barcodes, open-strip tracking, dose dispensing, genealogy, med history
```

## Read the docs

**Start here — onboarding & operations:**

- 📘 [Installation & Setup Guide](docs/INSTALLATION-GUIDE.md) — deploy from scratch (15 phases, with checkpoints + troubleshooting)
- ⚡ [Admin Quick Start](docs/ADMIN-QUICK-START.md) — the ~15-minute admin path
- 🧰 [Store Keeper Quick Start](docs/STOREKEEPER-QUICK-START.md) — the ~10-minute operator path
- 📜 [Historical v19.0.5 sign-off](docs/PRODUCTION-READINESS-v19.0.5.md) — preserved as the v19.0.5 production-readiness record; see CHANGELOG for the current release
- 💾 [Backup & Recovery Guide](docs/18-restore-drill.md) — encrypted backups + weekly restore drill
- 🎓 [Training Guide](docs/21-training-system.md) — the in-app Help & Training academy
- 🔐 [Security Policy](SECURITY.md) — supported versions + how to report a vulnerability

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
- [`docs/22-gdrive-backup.md`](docs/22-gdrive-backup.md) — Google Drive off-site backup: setup, Backup Now, restore
- [`docs/PRODUCTION-READINESS-v19.0.5.md`](docs/PRODUCTION-READINESS-v19.0.5.md) — historical sign-off record (v19.0.5)
- [`docs/RUN-AS-SERVICE.md`](docs/RUN-AS-SERVICE.md) — run Odoo as an auto-starting Windows service
- [`docs/LABEL-PRINTING.md`](docs/LABEL-PRINTING.md) — thermal 4×1 labels + printer gap calibration
- [`docs/ISSUE-DIMENSIONS.md`](docs/ISSUE-DIMENSIONS.md) — Department / Purpose / Animal on every Scan Issue + consumption-by-department
- [`docs/UOM-BY-KIND.md`](docs/UOM-BY-KIND.md) — product Kind sets the base unit at onboarding (fluid → Litre, feed → kg, else Units)
- [`docs/RETURNABLE-ITEMS.md`](docs/RETURNABLE-ITEMS.md) — returnable items, expected-return SLA, overdue alert + Returns-due report
- [`docs/ISSUE-APPROVALS.md`](docs/ISSUE-APPROVALS.md) — min-life re-request guard + high-value threshold → manager-only Approvals queue

**v20 Perishable Engine — design package & pilot guide:**

- [`docs/v20-perishable-engine/`](docs/v20-perishable-engine/) — full design package (architecture, touch-point map, data model, test plan, functional spec, backlog)
- [`docs/v20-perishable-engine/10-pilot-release-v20.0.0-beta1.md`](docs/v20-perishable-engine/10-pilot-release-v20.0.0-beta1.md) — pilot release notes, operator checklist, rollback guide
- [`addons/wms_perishable/CHANGELOG.md`](addons/wms_perishable/CHANGELOG.md) — per-ticket changelog for all Wave-1 tickets (V20-001…021)
- [`addons/wms_perishable/README.md`](addons/wms_perishable/README.md) — module feature list, Hook API 1.0 reference, configuration

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
will print the generated PDF labels. Tested with True-Ally 4×1 inch (100×25 mm)
die-cut direct-thermal stock on a TSC TE244 (gap-sensor); layout is admin-
configurable so other label sizes work too. See [docs/LABEL-PRINTING.md](docs/LABEL-PRINTING.md).

## Run tests

```powershell
.venv\Scripts\activate
python .odoo\odoo-bin -c config\odoo.native.conf -d wms_test --test-enable --stop-after-init `
    -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports,wms_training,wms_perishable `
    --without-demo=all --test-tags wms,wms_audit,wms_delete,wms_health,wms_ui_cert
```

## Backup / restore

```powershell
scripts\backup-native.ps1            # Writes .\backups\wms-<timestamp>.dump.gpg + filestore zip

# Restore — see docs/07-deployment.md
scripts/restore-native.ps1 -BackupPath backups/wms-<timestamp>.dump.gpg
```

A weekly restore drill (`scripts/restore-drill.ps1`) verifies the most recent encrypted backup is still recoverable - the drill never touches the production database. See `docs/18-restore-drill.md` for the runbook.

Optionally, every encrypted backup set is also uploaded to Google Drive after the local backup completes (verified via Drive's `sha256Checksum`; failure-safe — a Drive error never fails the local backup). Setup + restore runbook: [docs/22-gdrive-backup.md](docs/22-gdrive-backup.md).

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
3. After merge, push an annotated tag to trigger the release:

```powershell
git tag -a v19.0.47.0.0 -m "Release v19.0.47.0.0"
git push origin v19.0.47.0.0
```

The `Release` GitHub Actions workflow fires on tags matching
`v[0-9]+.[0-9]+.[0-9]+.[0-9]+.[0-9]+` and publishes a GitHub Release with
an auto-generated changelog from `last_tag..HEAD --no-merges`.

> **v20 pilot builds** use the tag format `v20.0.0-beta1` (not the 5-part
> numeric pattern), so they do NOT trigger the release workflow — they remain
> branch-only pilot artifacts until `v20 → main` after the pilot.

## License

LGPL-3 (matches Odoo CE).

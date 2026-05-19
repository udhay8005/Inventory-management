# Inventory_mngt — Odoo CE 19 WMS

Production-ready Warehouse Management System on Odoo 19 Community Edition,
purpose-built for an internal-stock trust (no sales, no invoices, no money).

**What's in the box:**

- 🏗 **Visual rack builder** — Rack → Compartment → Slot, plus open Floor Zones, with a per-rack flexible grid (4-way D-pad merging)
- 📦 **Scan-driven workflows** — Scan Receipt / Scan Return / Scan Issue (FIFO across slots) / Scan-Validate
- 🧾 **Audit trail invariant** — every stock-moving action records `wms_taken_by` / `wms_ordered_by` / `wms_storekeeper_id` on the resulting `stock.picking` plus a chatter message
- 👥 **Two-role security** — WMS Manager (Admin) vs WMS Store Keeper, with an admin-maintained roster of human keepers
- 🔧 **Damage / Repair workflow** — smart recommendation engine (urgent buy / repair / note only) + one-click Create Repair Order, full state machine (draft → in_repair → done / scrapped / cancelled) with chatter audit on every transition
- 🏷 **Thermal labels** — customisable 4×1 inch layout (logo zone + content zone), barcode rendered inline
- 🔁 **Returnability classification** — product Kind (Raw / Packaging / Fluid / Finished Good / WIP / Consumable / Tool / Spare) drives whether Scan Return accepts it
- 📈 **Buying recommendations** — daily-average usage + 7-day buffer for non-returnables; concurrent-users heuristic for tools/spares
- 📊 **Reports** — Where-is-it / Warehouse map / Oldest stock (FIFO) / Slot occupancy / Cycle count due / Movement history / Low stock alerts / Dead stock / Reorder summary
- 🤖 **Offline AI demand forecasting** — statsmodels-based, runs locally, no external API
- 🐳 **One-command bring-up** — Docker Compose with Odoo + PostgreSQL 16 + optional AI worker

## Quickstart

```bash
cp .env.example .env       # edit and change passwords
docker compose build
docker compose up -d
```

Open <http://localhost:8069/web/database/manager>, create a database with the
master password from `.env`, then in Apps **install in this order**:

1. `wms_location` — racks, slots, floor zones, role groups
2. `wms_fifo` — FIFO removal across slots
3. `wms_barcode` — scan wizards, barcode aliases, storekeeper roster, thermal labels
4. `wms_repair_damage` — damage / repair / return workflows
5. `wms_ai_forecast` — offline statsmodels forecasting + reorder
6. `wms_reports` — SQL-view dashboards

The `wms_location` module ships demo data with a sample rack, floor zones, and
seed products so you can click through immediately. Use **WMS → Configuration
→ Create Rack** or **Generate Floor Zones** to add more.

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

## Project layout

```
Inventory_mngt/
├── docker-compose.yml          Odoo + Postgres + optional AI worker + Cloudflare tunnels
├── Dockerfile                  Odoo CE 19 + python deps
├── requirements.txt            statsmodels, pandas, reportlab, etc.
├── config/odoo.conf
├── scripts/
│   ├── init-db.sh              first-boot DB grants
│   └── backup.sh               nightly pg_dump + filestore tarball
├── ai_worker/                  optional out-of-process forecast runner
├── docs/                       architecture & design notes (read these first!)
└── addons/
    ├── wms_location/           Rack/Compartment/Slot model + role groups + rack builder OWL component
    ├── wms_fifo/               FIFO removal across slots + partial index
    ├── wms_barcode/            scan wizards + barcode aliases + storekeeper roster + label printing
    ├── wms_repair_damage/      damage / repair / return flows + recommendation engine
    ├── wms_ai_forecast/        offline statsmodels forecasting + reorder
    └── wms_reports/            SQL-view dashboards (Where-is-it, FIFO age, occupancy, ...)
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

## Mobile access (phones / tablets / off-site)

Three options — pick whichever fits. Full setup in
[docs/12-mobile-access.md](docs/12-mobile-access.md):

- **Same-WiFi**: `http://<host-IP>:8069` after `New-NetFirewallRule -DisplayName "WMS Odoo 8069" -Direction Inbound -LocalPort 8069 -Protocol TCP -Action Allow`.
- **Cloudflare quick tunnel** (HTTPS, no account, random URL):
  `docker compose --profile tunnel up -d cloudflared_quick`
- **Cloudflare named tunnel** (permanent HTTPS URL on your domain):
  `CLOUDFLARE_TUNNEL_TOKEN=… docker compose --profile tunnel-named up -d cloudflared_named`

The scan wizards are mobile-responsive and open the device camera for the
optional item photo (required for liquid / weight / volume items).

## Hardware

USB / Bluetooth HID barcode scanners "just work" — they keyboard-type into the
focused field on the scan wizards. Any thermal printer your **host OS** can see
will print the generated PDF labels through the user's browser. Tested with
4×1 inch direct-thermal stock; layout is admin-configurable so other label
sizes work too.

## Run tests

```bash
docker compose run --rm odoo \
  odoo --test-enable --stop-after-init -d ci_test \
       -i wms_location,wms_fifo,wms_barcode,wms_repair_damage,wms_ai_forecast,wms_reports \
       --log-level=test
```

## Backup / restore

```bash
./scripts/backup.sh                  # writes to ./backups/
# Restore: see docs/07-deployment.md
```

## CI / CD

GitHub Actions pipeline runs on every push and PR — see [docs/17-ci-cd.md](docs/17-ci-cd.md).
Five jobs: lint (black / isort / flake8 / pylint-odoo / XML well-formedness),
security scan (bandit / pip-audit), Odoo module tests with `--test-enable`,
Docker compose smoke, and an aggregate `CI status` check used by branch
protection.

```bash
make help            # show every dev command
make lint            # same checks CI runs (black, isort, flake8, xml)
make test            # full Odoo test suite (slow)
make test-fast MOD=wms_location   # one module
make ci              # lint + test, exactly what CI runs
make format          # auto-fix style
```

Pre-commit hooks mirror CI locally:

```bash
pip install pre-commit && pre-commit install
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

## Firewall setup

```powershell
# Right-click PowerShell → Run as Administrator, then:
New-NetFirewallRule -DisplayName "WMS Odoo" -Direction Inbound -LocalPort 8069 -Protocol TCP -Action Allow
```

## License

LGPL-3 (matches Odoo CE).

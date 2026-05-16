# Inventory_mngt — Odoo CE 19 WMS

Production-ready Inventory Management System on Odoo 19 Community Edition, with
**slot-level location tracking (Rack → 6 Dividers → 3 Slots)**, **strict FIFO
picking**, **barcode scan/print**, **damage & repair workflows**, and **offline
AI demand forecasting**.

## Quickstart

```bash
cp .env.example .env       # edit and change passwords
docker compose build
docker compose up -d
```

Open <http://localhost:8069/web/database/manager>, create a database with the
master password from `.env`, then in Apps **install in this order**:

1. `wms_location`
2. `wms_fifo`
3. `wms_barcode`
4. `wms_repair_damage`
5. `wms_ai_forecast`
6. `wms_reports`

The `wms_location` module ships demo data that creates one rack `R-01` with all
18 slots so you can click through immediately. Use **WMS → Configuration →
Generate Rack** to add more.

## Project layout

```
Inventory_mngt/
├── docker-compose.yml          Odoo + Postgres + optional AI worker
├── Dockerfile                  Odoo CE 19 + python deps
├── requirements.txt            statsmodels, pandas, reportlab, etc.
├── config/odoo.conf
├── scripts/
│   ├── init-db.sh              first-boot DB grants
│   └── backup.sh               nightly pg_dump + filestore tarball
├── ai_worker/                  optional out-of-process forecast runner
├── docs/                       architecture & design notes (read these first!)
└── addons/
    ├── wms_location/           Rack/Divider/Slot model + wizard
    ├── wms_fifo/               FIFO removal across slots + partial index
    ├── wms_barcode/            scan wizards + label printing
    ├── wms_repair_damage/      damage / repair / return flows
    ├── wms_ai_forecast/        offline statsmodels forecasting + reorder
    └── wms_reports/            SQL-view dashboards (FIFO age, occupancy, ...)
```

## Read the docs

The most important docs:

- [`docs/01-architecture.md`](docs/01-architecture.md) — stack & layering
- [`docs/02-data-model.md`](docs/02-data-model.md) — why we extend `stock.location`
- [`docs/03-workflows.md`](docs/03-workflows.md) — inbound/outbound/repair flows
- [`docs/05-ai-prediction.md`](docs/05-ai-prediction.md) — algorithm choice + offline footprint
- [`docs/09-roadmap.md`](docs/09-roadmap.md) — phased build plan
- [`docs/10-testing.md`](docs/10-testing.md) — test strategy
- [`docs/11-maintenance.md`](docs/11-maintenance.md) — upgrades, tuning, FAQ

## Mobile access (phones / tablets / off-site)

Three options — pick whichever fits. Full setup in
[docs/12-mobile-access.md](docs/12-mobile-access.md):

- **Same-WiFi**: `http://<host-IP>:8169` after `New-NetFirewallRule -DisplayName "WMS Odoo 8169" -Direction Inbound -LocalPort 8169 -Protocol TCP -Action Allow`.
- **Cloudflare quick tunnel** (HTTPS, no account, random URL):
  `docker compose --profile tunnel up -d cloudflared_quick`
- **Cloudflare named tunnel** (permanent HTTPS URL on your domain):
  `CLOUDFLARE_TUNNEL_TOKEN=… docker compose --profile tunnel-named up -d cloudflared_named`

The scan wizards are mobile-responsive and open the device camera for the
optional item photo (required for liquid / weight / volume items).

## Hardware

USB / Bluetooth HID barcode scanners "just work" — they keyboard-type into the
focused field on the scan wizards. Any thermal printer your **host OS** can see
will print the generated PDF labels through the user's browser.

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

GitHub Actions pipeline on every push and PR — see [docs/17-ci-cd.md](docs/17-ci-cd.md).

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

## Firewall setpup
```bash
# Right-click PowerShell → Run as Administrator, then:
New-NetFirewallRule -DisplayName "WMS Odoo" -Direction Inbound -LocalPort 8169 -Protocol TCP -Action Allow
```

## License

LGPL-3 (matches Odoo CE).

## Inventory-management

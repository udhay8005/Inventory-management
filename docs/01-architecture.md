# 01 — Architecture overview

## Stack

| Layer | Choice | Why |
|---|---|---|
| ERP core | **Odoo CE 19** | Free, mature inventory + barcode primitives, audited security |
| DB | **PostgreSQL 15 / 16 / 17 (auto-detected)** | Odoo's native DB; the install script detects whichever postgresql-x64 service is present. Supports partial indexes for fast quant lookups |
| Forecasting | **statsmodels (Holt-Winters / SES)** | CPU-only, ~30MB resident, runs on a Pi 4 |
| Deployment | **Native Windows (no Docker)** | `scripts/install-native.ps1` + `start-native.ps1`; Odoo runs in a venv against the local PostgreSQL service. Docker was removed. |
| Optional AI worker | Native Python process (`scripts/start-ai-worker.ps1`) | Detach forecasts from Odoo when memory is tight |

## Module layering

```
+----------------------------------------------------+
| wms_reports        (dashboards, printable reports) |
+----------------------------------------------------+
| wms_ai_forecast    (offline trend / reorder AI)    |
+----------------------------------------------------+
| wms_repair_damage  (damage/repair/return flows)    |
+----------------------------------------------------+
| wms_barcode        (scan wizards, label printing)  |
+----------------------------------------------------+
| wms_fifo           (FIFO removal strategy)         |
+----------------------------------------------------+
| wms_location    (rack/compartment/slot data model) |
+----------------------------------------------------+
| Odoo CE 19 stock, product, purchase, repair        |
+----------------------------------------------------+
```

Each module above the line only depends on what's below it. `wms_location` is
the foundation; everything else degrades gracefully without the AI module.

## Design principles

1. **Reuse, never replace.** Rack/Compartment/Slot are `stock.location` records,
   not a parallel table (a compartment is a shelf×column span within a rack's 2D
   grid, not a separate "level" entity). Every `stock.quant` movement keeps
   working unchanged.
2. **Deterministic before AI.** Reorder math is rule-based (ROP, safety stock).
   AI only adjusts the *forecast* that feeds those rules.
3. **One source of truth for quantity.** Never duplicate qty across tables.
   `stock.quant` is canonical; everything else is a view or derived report.
4. **Audit trail by construction.** Every transition is a `stock.move`. Damage,
   repair, return are state-machine wrappers that *generate* moves — they don't
   bypass them.

## Process model

- **Single native Odoo process** runs HTTP workers + cron threads (default),
  started by `scripts/start-native.ps1` against the local PostgreSQL service.
- **Optional AI worker** for ops who prefer separation (`scripts/start-ai-worker.ps1`).
- **No external services** required. All AI is local.

## Networking

- Odoo listens on `localhost:8069` (HTTP + WebSocket share the port; `workers = 0`).
- For remote access, `scripts/start-tunnel.ps1` fronts it with a Cloudflare tunnel
  (HTTPS). Behind a reverse proxy, set `proxy_mode = True`.
- The database-manager web UI is disabled (`list_db = False`, `db_listing = False`).

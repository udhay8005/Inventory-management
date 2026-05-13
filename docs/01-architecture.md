# 01 — Architecture overview

## Stack

| Layer | Choice | Why |
|---|---|---|
| ERP core | **Odoo CE 19** | Free, mature inventory + barcode primitives, audited security |
| DB | **PostgreSQL 16** | Odoo's native DB; supports partial indexes for fast quant lookups |
| Forecasting | **statsmodels (Holt-Winters / SES)** | CPU-only, ~30MB resident, runs on a Pi 4 |
| Container | **Docker Compose** | Single command bring-up; mount addons read-write for dev |
| Optional AI worker | Python 3.12 slim container | Detach forecasts from Odoo when memory is tight |

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
| wms_location       (rack/divider/slot data model)  |
+----------------------------------------------------+
| Odoo CE 19 stock, product, purchase, repair        |
+----------------------------------------------------+
```

Each module above the line only depends on what's below it. `wms_location` is
the foundation; everything else degrades gracefully without the AI module.

## Design principles

1. **Reuse, never replace.** Rack/Divider/Slot are `stock.location` records, not
   a parallel table. Every `stock.quant` movement keeps working unchanged.
2. **Deterministic before AI.** Reorder math is rule-based (ROP, safety stock).
   AI only adjusts the *forecast* that feeds those rules.
3. **One source of truth for quantity.** Never duplicate qty across tables.
   `stock.quant` is canonical; everything else is a view or derived report.
4. **Audit trail by construction.** Every transition is a `stock.move`. Damage,
   repair, return are state-machine wrappers that *generate* moves — they don't
   bypass them.

## Process model

- **Single Odoo container** runs HTTP workers + cron threads (default).
- **Optional AI worker** for ops who prefer separation (compose profile `ai`).
- **No external services** required. All AI is local.

## Networking

- `db` and `odoo` on private bridge; only Odoo's 8069/8072 published.
- For HTTPS, put nginx/Caddy in front; set `proxy_mode = True` (already set).

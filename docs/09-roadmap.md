# 09 — Implementation roadmap

## Phase 0 — Bring-up (Day 1)
- [x] Docker compose, Dockerfile, odoo.conf, env example
- [x] Doc skeleton
- [x] Migrated off Docker to native Windows install (PostgreSQL service + Python venv + Odoo source clone). See `scripts\install-native.ps1`.

## Phase 1 — Core hierarchy (Days 2-4) — `wms_location`
- [x] `stock.location` extension with `wms_location_type` + position fields
- [x] Constraints on the Rack → Compartment → Slot hierarchy (6 shelves × 3 columns per rack by default)
- [x] `wms.rack.generator` wizard to spin up a rack with all slots in one click
- [x] Tree, kanban, search views for slots
- [x] Demo data: 1 warehouse, 1 demo rack (R-01) with auto-generated compartments + slots, demo products

## Phase 2 — FIFO removal (Day 5) — `wms_fifo`
- [x] Register `removal_strategy = wms_fifo_global` on stock.location.route
- [x] Server method that sorts quants by `in_date ASC` across all child slots
- [x] Apply by default to the Stock parent location

## Phase 3 — Barcode (Days 6-8) — `wms_barcode`
- [x] `wms.barcode.alias` (carton barcodes)
- [x] *Scan Receipt* wizard
- [x] *Scan Issue* wizard (FIFO-driven)
- [x] Label report templates (product / slot / rack)
- [x] Server actions to print

## Phase 4 — Damage / Repair / Return (Days 9-11) — `wms_repair_damage`
- [x] `wms.damage` model + flow
- [x] `wms.repair.order` state machine
- [x] Damage / Repair-out internal locations auto-created per warehouse
- [x] Return → original-slot suggestion

## Phase 5 — AI forecast (Days 12-14) — `wms_ai_forecast`
- [x] `wms.forecast` + `wms.forecast.history`
- [x] `wms.forecast.engine` (statsmodels)
- [x] Daily cron
- [x] Reorder math (deterministic) + push-to-PO action
- [x] Consumable vs reusable branch

## Phase 6 — Reports (Days 15-17) — `wms_reports`
- [x] ~20 SQL-view dashboards
- [x] Printable PDFs (rack occupancy, reorder PO draft, weekly damage)

## Phase 7 — Hardening (Days 18-20)
- [x] Load test with 100k quants — perf budget documented (FIFO query < 50 ms on 100k `stock.quant` rows) shipped (see `docs/10-testing.md` §Performance benchmarks)
- [x] Permission matrix verified — capability sub-groups (`group_wms_can_scan_receive` / `_scan_issue` / `_file_damage` / `_submit_audit` / `_manage_catalog`) shipped in v19.0.10.0.0
- [x] Restore drill from backup — `WMS Weekly Restore Drill` scheduled task shipped in v19.0.9.0.0
- [x] User training docs — `wms_training` addon (Help Center, guided tours, SOPs, annotated SVGs, beginner-mode) shipped across v19.0.1.0.0 – v19.0.8.0.0

## Stretch (post-MVP)
- Mobile-friendly scanner page — _shipped_: scan wizards are mobile-responsive and open the device camera (see `docs/12-mobile-access.md`)
- Multi-warehouse routing
- ABC analysis on top of forecast
- Vendor scorecard from forecast accuracy

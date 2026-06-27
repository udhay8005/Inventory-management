# Changelog — wms_analytics (v20 Wave 2: Warehouse Intelligence)

## 19.0.2.0.0 — Wave 2 (branch `v20-wave2-3`) — 2026-06-27

First release of the Wave 2 analytics layer. Additive over the Wave 1 stack — it
reads the Wave 1 data (lots, quants, forecast, damage, recall, quarantine) and
owns new reporting models; it `_inherit`-extends Wave 1 models only to add new
fields (audit score, supplier links, cold-chain temp band, forecast risk). No
Wave 1 file is edited. Depends on `wms_perishable` + `wms_ai_forecast`.

Full `wms_analytics` suite: **60 tests, 0 failed / 0 error**; full 9-addon
regression **587 tests, 0 failed / 0 error**; black / isort / flake8 clean.

### Added — all 15 Wave 2 features

- **#1 KPI Dashboard** — `/wms/intelligence`, 13 real-time KPI tiles (total
  inventory, value, near-expiry, expired, recalled, quarantined, damaged,
  under-repair, dead/fast/slow moving, overstock, low-stock) + health score +
  expiry-risk counts. Manager-gated.
- **#2 Expiry Risk Engine** ⭐ — `wms.lot.expiry.risk` SQL view: joins per-lot
  on-hand to forecast consumption velocity → days-of-cover vs remaining shelf
  life → LOW / MEDIUM / HIGH / CRITICAL band + value-at-risk. List/pivot/graph.
- **#3 AI Forecast risk** — weekly demand + overstock/understock risk on
  `wms.forecast` (`_inherit`).
- **#4 Supplier Analytics** — `wms.supplier.scorecard` (lots, recalls, QC
  rejects, damaged/expired, acceptance/rejection rate, 0–100 quality score) +
  `wms.supplier.ledger`. Supplier links added to damage & quarantine.
- **#5 Disposal Analytics** — `wms.disposal.report` (damage + destroyed lots,
  reason, value, monthly trend).
- **#6 Stock Health Score** — `wms.stock.health`: on-hand classified Recall >
  Quarantine > Expired > Near > Healthy, with percentages + overall score.
- **#7 KPI trends** — `wms.occupancy.snapshot` (daily cron) for occupancy over
  time + `wms.fefo.compliance` SQL view (was the issued lot the earliest-expiry?).
- **#8 Advanced Ledgers** — `wms.lot.ledger`, `wms.product.ledger`,
  `wms.warehouse.ledger` (movement history) + `wms.department.usage`,
  `wms.animal.usage`, `wms.medicine.consumption`.
- **#9 Recall Dashboard** — issued / remaining / destroyed / returned / open
  roll-ups on `wms.lot.recall` + graph/pivot.
- **#10 Lot Audit Score** — 7-check traceability completeness on `stock.lot`
  (batch / supplier / barcode / expiry / timeline / movement / storage).
- **#11 Heat Map** — `/wms/intelligence/heatmap`: rack/floor tiles coloured by
  worst status (Recall > Quarantine > Expired > Near-expiry) with occupancy
  fallback + legend.
- **#12 Cold Chain** — product temperature band (default 2–8 °C for vaccines) +
  `wms.cold.chain.reading`; an out-of-range reading auto-quarantines the lot.
- **#13 Bulk Operations** — select many lots → recall / quarantine / destroy
  server actions (manager-gated).
- **#14 Cycle-Count Intelligence** — `wms.cycle.count.priority`: risk-scored
  count prioritisation (age + audit-variance history + velocity).
- **#15 Advanced Traceability** — `wms.lot.traceability` SQL view: supplier →
  shelf → first issue → animal → repair → destroy in one row per lot.

All new models carry ACLs (manager + user); menus live under WMS ▸ Intelligence.

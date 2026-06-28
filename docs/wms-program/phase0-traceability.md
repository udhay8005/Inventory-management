# WMS Engineering Program — Phase 0: Repository Analysis & Wave 1/2/3 Traceability

**Date:** 2026-06-27 · **Branch:** `v20` · **HEAD:** `15a0388` · **Working tree:** clean
**Method:** 22 independent read-only auditors (one per feature + inventory/CI), each required to
cite `file:line` evidence; no code modified. Static analysis only — verdicts reflect code presence
and wiring, not a live `--test-enable` run (that is Phase 1's executable confirmation).

> **Stack note:** the whole project targets **Odoo 19.0 CE**. The "v20" label is the *project*
> major (Universal Perishable Engine), not the Odoo major — `wms_perishable` is version `19.0.1.19.0`.

---

## 1. Executive summary

| Wave | Implemented | Partial | Missing | Verdict |
|------|:-----------:|:-------:|:-------:|---------|
| **Wave 1** (Operational Engine) | 2 of 3 groups | 1 (per-kind shelf-life only) | 0 | **Complete as owner-frozen scope** |
| **Wave 2** (Warehouse Intelligence) | 0 | 7 | 8 | **Not started (mostly)** |
| **Wave 3** (Pharmacy) | 0 | 0 | 2 | **Not started** |

The one Wave 1 "partial" is the **per-kind shelf-life table** (spec §2.8 / ticket **V20-022**),
which the owner **explicitly deferred** at sign-off (OWNER-9 chose "warn + manager approval", which
is the global near-expiry guard that *is* built and wired). So Wave 1 is **complete against its
frozen scope**; V20-022 is a documented optional enhancement, not a defect.

---

## 2. Module inventory

| Addon | Version | Role | Depends |
|-------|---------|------|---------|
| wms_location | 19.0.3.25.0 | Rack→Compartment→Slot model; application root | barcodes, mail, product, stock, web |
| wms_fifo | 19.0.1.1.0 | Global FIFO override on `stock.quant._gather` + partial index | wms_location |
| wms_barcode | 19.0.1.48.0 | Scan receive/issue, carton aliases, thermal labels, issue-approval | wms_location, wms_fifo, stock, barcodes, mail |
| wms_repair_damage | 19.0.1.17.0 | Damage/repair/return workflows → auditable stock moves | wms_location, wms_barcode, stock, mail |
| wms_ai_forecast | 19.0.1.5.0 | Holt-Winters/SES demand forecast + reorder math | wms_location, wms_barcode, stock, purchase |
| wms_reports | 19.0.4.14.0 | SQL-view reports + dashboard + backup/DR observability | wms_location, wms_ai_forecast, wms_repair_damage, stock |
| wms_training | 19.0.1.14.0 | In-app help, training, tutorials, Beginner Mode | wms_location, web, wms_barcode, wms_reports, wms_repair_damage |
| wms_perishable | 19.0.1.19.0 | Per-lot expiry + FEFO + quarantine/recall (Wave 1) | wms_location, wms_fifo, wms_barcode, wms_repair_damage, wms_reports, product_expiry |

Only **wms_location** is `application: True`; all 8 are installable. External Python deps:
`wms_ai_forecast` → statsmodels, pandas, numpy. Only `wms_ai_forecast` depends on `purchase`;
only `wms_perishable` depends on `product_expiry`.

**Load order (topological):** wms_location → wms_fifo → wms_barcode → {wms_repair_damage,
wms_ai_forecast} → wms_reports → wms_training → wms_perishable.

**File totals:** 56 model `.py`, 55 view `.xml`, 11 wizard `.py`, 21 data `.xml`, 75 ACL rows.
Heaviest module: **wms_reports** (16 models, 21 views, 21 ACL rows).

---

## 3. CI / test / security / git baseline

**CI** (`.github/workflows/ci.yml`) — 6 jobs on push/PR to `main|test|v20`: `lint`
(black/isort/flake8/pylint-odoo/XML/PowerShell), `security` (bandit `-ll` + pip-audit `--strict`),
`odoo_tests` (installs all 8 addons, `--test-enable`, **fail-on-skip guard**), `odoo_upgrade`
(`v19.0.46.0.0` → HEAD; 7 addons — wms_perishable excluded as it didn't exist at PREV_TAG),
`native_smoke` (HTTP 200/303 on `/web/login`), `ci_status` (single required check).

**Tests** — **519 methods across 90 `test_*.py` files**:

| addon | files | methods |
|-------|:-----:|:-------:|
| wms_reports | 26 | 200 |
| wms_barcode | 19 | 138 |
| wms_location | 12 | 82 |
| wms_perishable | 20 | 66 |
| wms_training | 4 | 15 |
| wms_repair_damage | 8 | 14 |
| wms_ai_forecast | 1 | 4 |
| wms_fifo | 0 | 0 |
| **total** | **90** | **519** |

**Security** — ACL-only (no `ir.rule` records anywhere). `.flake8`, `pyproject.toml`
(`[tool.black]`/`[tool.isort]`/`[tool.bandit]`), `.pre-commit-config.yaml` all present.

**Git** — branch `v20`, clean tree, 59 tags (`v19.0.1.0.0`…`v19.0.46.0.0` + `v20.0.0-beta1`).

---

## 4. Wave 1 traceability — Operational Engine

| # | Feature group | Status | Evidence (representative) | Gap |
|---|---------------|--------|---------------------------|-----|
| W1a | FIFO, FEFO, per-lot expiry, near-expiry guard, **per-kind shelf-life** | **PARTIAL** | `wms_fifo/models/stock_quant.py:7-40` (FIFO `_gather`); `wms_perishable/models/stock_quant.py:67-102` (FEFO `_wms_sorted_for_removal`); `:17-42` (`wms_effective_expiry` stored+indexed); `scan_receipt.py:42-112` (near-expiry guard, manager override) | **Per-kind shelf-life table (§2.8) NOT built** — only a single global param `wms_perishable.min_receive_shelf_life_days` (default 60). **No short-dated-ISSUE guard.** Deferred to **V20-022** by owner (OWNER-9). |
| W1b | Recall, Quarantine, Repair, Damage, Returns | **IMPLEMENTED** | `wms_lot_recall.py:68-115`; `wms_lot_quarantine.py:69-131`; `stock_location.py:55-71` (issue-exclusion gate); `wms_repair_order.py:178-298`; `wms_damage.py:413-486`; `scan_receipt.py:370-417` (returns) | None blocking. Quarantine "destroyed" is a state flag; physical write-off move deferred to Wave 2 disposal. |
| W1c | Product mgmt, Barcode, Rack/Slot, Movement history, Lot timeline, Lot barcode, base Reports, Migration, Security, Testing, Docs | **IMPLEMENTED** | `product_template.py` (18 kinds, immutable code+SKU); `wms_barcode_alias.py:13-67`; `wms_label_printer.py` (TSPL); `stock_location.py` (rack hierarchy); `wms_storekeeper_activity.py` (movement SQL view); `stock_lot.py:94-163` (timeline + label); `wms_lot_migration.py` | Thin test coverage on wms_ai_forecast (1 file) / wms_training (4). |

### Phase 1 verdict (Wave 1 compliance)

**Wave 1 is COMPLETE against the owner-frozen scope.** 20 of 21 backlog tickets implemented and
wired; V20-006 (dup-lot dialog), V20-022 (per-kind shelf-life), V20-023 (lot lock) were deferred by
owner decision and are documented as such. The single "partial" (per-kind shelf-life) reflects a
**deferred-by-owner** optional enhancement, not an incomplete requirement.

---

## 5. Wave 2 traceability — Warehouse Intelligence

| # | Feature | Status | What exists | What's missing |
|---|---------|--------|-------------|----------------|
| 1 | Analytics Dashboard (KPI tiles) | **PARTIAL** | Server-rendered `/wms/dashboard` (QWeb, manager-gated) with 4 grouped cards; ~5 of 13 KPIs present | Inventory Value, Recalled, Quarantined, Fast/Slow Moving tiles; split Near-Expiry/Expired; **Overstock has no backing data**; no in-app OWL/tile dashboard |
| 2 | **Expiry Risk Engine** ⭐ | **MISSING** | Days-to-expiry banding (`wms.lot.expiry.alert`) + per-product forecast (`wms.forecast`) exist **separately** | The engine joining shelf-life × consumption velocity → LOW/MED/HIGH/CRITICAL. No model/field/UI/test |
| 3 | AI Forecast | **PARTIAL** | `wms.forecast` (Holt-Winters/SES): daily/monthly avg, predicted qty, reorder qty/date, velocity class — wired, cron, PO push | **weekly demand**, **overstock risk**, **understock risk** not surfaced as outputs |
| 4 | Supplier Analytics | **MISSING** | `stock.lot.wms_supplier_id`/batch/invoice; recall `supplier_id` | Scorecard model; supplier link on damage & quarantine; scheduled-vs-actual receipt date (late delivery); quality/acceptance/rejection rates; UI/ACL |
| 5 | Disposal Analytics | **MISSING** | `wms.damage.damage_value` (per-event loss); scrap; destroyed-lot flag | Aggregated disposal/loss report; destroyed qty/date/value capture; monthly trend; pivot/graph; cron |
| 6 | Stock Health Score | **MISSING** | All inputs ready (`wms_lot_state`, expiry view) | Composite %Healthy/NearExpiry/Expired/Quarantine/Recall model + surfacing (backlog V20-037) |
| 7 | Warehouse KPI Dashboard (charts) | **PARTIAL** | `wms.storekeeper.activity` graph+pivot covers Issues/Receipts/Returns/Damage/Repairs by day/week/month | **Occupancy over time** (only point-in-time), **FEFO compliance** metric (absent), unified chart screen |
| 8 | Advanced Reporting (7 ledgers) | **MISSING** | Valuation/aggregation views exist but no ledgers | Lot/Product/Warehouse/Supplier ledgers, Department/Animal/Medicine usage; `wms.lot.traceability` SQL view (V20-036) |
| 9 | Recall Dashboard | **MISSING** | `wms.lot.recall` model (Wave 1) | issued/remaining/destroyed/returned/open-cases aggregates; supplier rollup; graph/pivot; report (V20-030) |
| 10 | Lot Audit Score | **MISSING** | All 7 checkable fields exist on `stock.lot` | Completeness score compute + rubric + UI badge + report |
| 11 | Warehouse Heat Map | **PARTIAL** | Real color-coded `/wms/warehouse/map` + `/wms/rack/<id>/grid` (wired, gated) | Color is **occupancy-only**; near-expiry/recall/damage/repair status not overlaid; no legend precedence; no tests |
| 12 | Cold Chain (vaccines) | **MISSING** | "vaccine" product kind; generic quarantine hold/release/reject | Temperature capture/range; vaccine cold-chain state machine; receipt-time reading; UI/ACL/tests |
| 13 | Bulk Operations | **PARTIAL** | Recall/quarantine accept M2M `lot_ids` (act on 500 at once) | No `stock.lot` list view; no `ir.actions.server` select-then-act; no "Approve" verb; batching/confirm |
| 14 | Cycle Count Intelligence | **PARTIAL** | Age-based `wms.cycle.count.due` (>30d) + weekly cron + dashboard tile (wired, tested) | High-risk scoring, mismatch frequency (from `wms.audit`), fast-moving weighting (from velocity); composite priority |
| 15 | Advanced Traceability | **PARTIAL** | Single-lot timeline (`action_wms_lot_timeline`) + supplier/batch metadata | End-to-end `wms.lot.traceability` SQL view (Supplier→PO→Receipt→Lot→Rack→Issue→Animal→Return→Repair→Destroy); UI/menu/ACL (V20-036) |

---

## 6. Wave 3 traceability — Pharmacy

| Feature | Status | What exists | What's missing |
|---------|--------|-------------|----------------|
| Packaging hierarchy + engine + nested barcode + strip-FEFO + open-strip | **MISSING** | Flat carton multiplier only (`wms.barcode.alias.units_per_scan`); pack size is free text | Box→Strip→Tablet tier model; `strips_per_box`/`tablets_per_strip`; tier-aware barcode resolver; strip-level FEFO; open/partial-strip quantity; open-package preference |
| Dispensing + genealogy + animal medication history | **MISSING** | `animal_id` captured on issue (wired, indexed); `wms.animal` register; medicine kind | Dose dispensing engine; box→strip→tablet→dose lineage; animal medication-history reverse O2M + smart button + report |

> **Architecture note:** `docs/PRODUCT-MASTER-ARCHITECTURE.md` deliberately rejected a nested
> packaging model for Wave 1 ("pack-as-template, own SKU+barcode; alias only for N-in-a-carton").
> Wave 3 introduces the hierarchy as a *new, additive* capability — it does not redesign Wave 1.

---

## 7. Build plan for Phases 2–6 (no code yet — pending owner sequencing decision)

**Phase 2 — Wave 1 completion:** only candidate is **V20-022** (per-kind shelf-life table +
short-dated-issue guard + settings UI). Owner-deferred → implement only if owner re-includes it.

**Phase 4 — Wave 2** (proposed new addon **`wms_analytics`**, additive, depends on the Wave 1 stack):
- *New subsystems:* Expiry Risk Engine, Supplier Analytics, Disposal Analytics, Stock Health Score,
  Advanced Ledgers (7), Recall Dashboard, Lot Audit Score, Cold Chain.
- *Enhancements in place:* complete the KPI dashboard tiles, AI-forecast weekly/overstock/understock
  outputs, occupancy-over-time + FEFO-compliance, heat-map status colors, bulk-operation server
  actions, cycle-count intelligence scoring, advanced traceability SQL view.

**Phase 6 — Wave 3** (proposed new addon **`wms_pharmacy`**, additive, depends on wms_perishable):
packaging tier model, tier-aware barcode resolver, strip-level FEFO, open-strip tracking, dose
dispensing engine, packaging genealogy, animal medication history.

**Governance flag:** the frozen change-control (functional spec §15) and the owner roadmap place
Wave 2 **after a 2–4 week warehouse pilot**. Building Wave 2/3 now on the `v20` branch (not merged,
not released) is compatible with the human-approval gate, but starting ahead of the pilot is an
owner sequencing decision to make consciously.

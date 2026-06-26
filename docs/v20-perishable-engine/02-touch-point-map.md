# v20 Touch-Point Map (Dependency Map)

Every place the engine touches, by subsystem, with file:line as of v19 (verify line numbers at
implementation time — they drift). Legend: **[INHERIT]** extend an existing model/view via
`_inherit`/xpath from `wms_perishable` (no v19 edit) · **[NEW]** new model/file in
`wms_perishable` · **[SURGICAL]** the rare case where a frozen-addon edit is unavoidable (make
it its own commit).

## A. FEFO removal engine + picker exclusion  (CORE)

| # | Where | Today | v20 |
|---|-------|-------|-----|
| A1 | `wms_location/models/stock_quant.py` → `_wms_sorted_for_removal()` (~L111–155) | FEFO branch keys on template `wms_expiry_date`, collapses to FIFO | **[INHERIT]** override: `super()` then sort on stored `wms_effective_expiry`; FIFO branch unchanged |
| A2 | `wms_location/models/stock_quant.py` (fields) | no per-lot expiry field | **[INHERIT]** add stored, indexed `wms_effective_expiry` = `lot.expiration_date or tmpl.wms_expiry_date` |
| A3 | `wms_location/models/stock_location.py` → `find_oldest_quants_for_product()` base_domain (~L335–341) | excludes `wms_is_damage`, `wms_is_repair` | **[INHERIT]** add `("location_id.wms_is_quarantine","=",False)`, `("location_id.wms_is_recall","=",False)`, and exclude recalled-lot quants |
| A4 | `wms_fifo/models/stock_quant.py` → `_gather()` override (~L7–40) | calls `_wms_sorted_for_removal()` | **no change** — auto-picks up A1 |
| A5 | `wms_fifo/hooks.py` partial index (~L20–26) `idx_quant_fifo (product_id, in_date)` | FIFO index | **[NEW]** add `idx_quant_fefo (product_id, wms_effective_expiry) WHERE quantity>0` (in `wms_perishable` post-init) |
| A6 | `wms_location/data/wms_data.xml` (~L10) sets `removal_fifo` | seeds Odoo strategy | **no change** (WMS engine sorts above it) |

## B. Locations — Quarantine / Recall  (reuse damage/repair pattern)

| # | Where | Today | v20 |
|---|-------|-------|-----|
| B1 | `wms_repair_damage/models/stock_location.py` (~L7–14) `wms_is_damage`, `wms_is_repair` | the exclusion-flag pattern | **[INHERIT]** add `wms_is_quarantine`, `wms_is_recall` (same shape) |
| B2 | `wms_repair_damage/hooks.py` → `post_init_locations()` (~L6) loop creates Damage/Repair-Out | auto-create pattern | **[NEW]** `wms_perishable` post-init: same loop creates Quarantine + Recalled under every WH `view_location_id` |

## C. Receipt — batch/expiry/supplier capture + lot creation

| # | Where | Today | v20 |
|---|-------|-------|-----|
| C1 | `wms_barcode/wizards/scan_receipt.py` → `WmsScanReceiptLine` (~L511–527) has `lot_id` | line model | **[INHERIT]** add `batch_number`, `expiry_date`, `manufacture_date`, `supplier_id`, `supplier_batch`, `supplier_invoice` |
| C2 | `scan_receipt.py` → `action_validate()` lot→move_line loop (~L253–298) | carries scanned `lot_id` to move lines | **[INHERIT]** before setting `ml.lot_id`: find/create `stock.lot` with `expiration_date`+supplier meta; **never merge** (each line → its lot); guard `product.tracking=='lot'` |
| C3 | `wms_barcode/models/wms_barcode_alias.py` → `resolve()` lot lookup (~L90) | finds lot by name | **[INHERIT]** add `_resolve_or_create_lot(product, batch, expiry)` helper (lookup-or-create, never merge) |
| C4 | `wms_barcode/wizards/scan_receipt_views.xml` line list (~L43–50) | columns product/qty/lot/dest | **[INHERIT/xpath]** add batch + expiry columns (visible), supplier cols (optional-hide) |
| C5 | (QC option) `action_validate()` destination | lands stock in the slot | **[INHERIT]** if perishable + QC-on: land in **Quarantine** location instead |

## D. Issue — FEFO preview + expired block + bypass warning  (reuse approval gate)

| # | Where | Today | v20 |
|---|-------|-------|-----|
| D1 | `wms_barcode/wizards/scan_issue.py` → `action_plan()` (~L608–676) builds plan, snapshots `expiry_date` from template | plan + feedback | **[INHERIT]** read per-lot expiry; detect expired-in-plan; compute resulting balances + FEFO order for the preview |
| D2 | `scan_issue.py` → `WmsScanIssuePlan` (~L1002–1021) has `expiry_date` | plan line model | **[INHERIT]** add `lot_id`, `resulting_balance`; (UI) FEFO-order + balances |
| D3 | `scan_issue.py` → `action_validate()` approval gate (~L740–767), `_approval_gate_enabled()` (~L445), `_create_approval()` (~L550–594) | high-value/min-life gate → held approval | **[INHERIT]** add `_check_expired()`; if expired → require reason → snapshot to approval (`reason_expired`) → hold |
| D4 | `wms_barcode/models/wms_issue_approval.py` reason fields (~L46–58), `action_approve()` (~L152–289), line has `expiry_date` (~L438) | approval model + flow | **[INHERIT]** add `reason_expired` + `expired_*`; re-check still-expired at approve time |
| D5 | `wms_barcode/wizards/scan_issue_views.xml` plan list + decorations (~L40–51), approval-reason box (~L148–170) | colour cues + reason box | **[INHERIT/xpath]** FEFO-bypass warning banner; resulting-balance preview; expired alert |
| D6 | `wms_barcode/security/wms_approval_security.xml` `group_wms_can_approve_issue` | manager-gated approve | **no change** — reuse as-is |

## E. Product model + creation wizards — universal perishable kinds + auto-enable

| # | Where | Today | v20 |
|---|-------|-------|-----|
| E1 | `wms_location/models/product_template.py` `EXPIRY_SENSITIVE_KINDS` (~L101) = {medicine,feed,fluid,pooja} | perishable switch | **[INHERIT]** extend: + vaccine, supplement, chemical, fertilizer, food (+ their `WMS_KIND_SELECTION`, `KIND_DEFAULT_UOM`, `KIND_RETURNABLE_DEFAULTS`, `KIND_SKU_PREFIX`, `KIND_SEQ_CODE`, sequences XML) |
| E2 | `product_template.py` → `create()` (~L637–730) | stamps SKU/PRD/barcode | **[INHERIT]** for perishable kinds set `tracking='lot'` + `use_expiration_date=True` (only on NEW products) |
| E3 | `product_template.py` `wms_expiry_date` (~L409–416), `wms_batch_number` (~L417–422) | template-level expiry/batch | keep as **fallback** for non-lot products + form display |
| E4 | `wms_barcode/wizards/wms_product_create.py` (~L214–236 `_create_product`) | guided create, no expiry field | **[INHERIT]** add conditional `wms_expiry_date`; pass through to `create()` |
| E5 | `wms_barcode/wizards/wms_product_onboard.py` validation (~L135) + `_do_onboard` (already passes expiry) | bulk onboard | **[INHERIT]** extend the required-expiry kind list to the new perishables |
| E6 | `wms_product_create_views.xml` / `wms_product_onboard_views.xml` | expiry conditional | **[INHERIT/xpath]** show/require expiry for the extended perishable set |

## F. Reports + cron + dashboard

| # | Where | Today | v20 |
|---|-------|-------|-----|
| F1 | `wms_reports/models/wms_expiry_alert.py` SQL view (~L75–125), status CASE 30/90 (~L114–119), `_cron_post_expiry_digest` (~L131–175) | template-date view + weekly digest | **[INHERIT/replace view]** re-key to `stock.lot.expiration_date` (fallback template); add `lot_id`, `batch`, `recall_status`; thresholds from settings |
| F2 | `wms_reports/models/wms_oldest_stock_report.py` (`_order="in_date asc"`) | FIFO age view | **no change** (stays the FIFO view) |
| F3 | `wms_reports/data/cron.xml` (weekly digest ~L26–37; daily patterns ~L50–61) | cron pattern | **[NEW]** optional daily threshold cron + hourly active-recall check (reuse `notify_wms_managers`) |
| F4 | `wms_reports/views/menus.xml` `menu_wms_reports_alerts` (~L79–107) | menu tree | **[NEW]** menuitems: lot ledger, lot recalls, traceability, perishable dashboard |
| F5 | `wms_reports/views/dashboard_template.xml` + `controllers/main.py` (~L159–243) `/wms/dashboard` | dashboard pattern | **[NEW]** `/wms/perishable-dashboard` route + template: expired/urgent/soon/ok counts, value-at-risk, quarantine, recalls |
| F6 | `wms_reports/models/wms_self_diagnostics.py` `_PROBES` (~L12–64) | integrity probes | **[INHERIT]** add 2 probes: perishable lots w/o expiry; perishable on-hand w/o lot |
| F7 | `wms_reports/models/wms_notify.py` `notify_wms_managers` (~L23–53); `wms_returns_due.py` (the `_auto=False` SQL-view + tz-safe date pattern) | reusable helpers | **reuse** for every new alert + report (do not reinvent) |

## G. Cross-cutting — damage / repair / return keep the lot

| # | Where | Today | v20 |
|---|-------|-------|-----|
| G1 | `wms_repair_damage/models/wms_damage.py` move create (~L464–486), quant search excludes damage/repair (~L224–233) | no `lot_id` on damage move | **[INHERIT]** read source-slot quants → carry `lot_id` onto the move/move-line; error if a slot holds >1 lot of the product (ambiguous) |
| G2 | `wms_repair_damage/models/wms_repair_order.py` start/finish moves (~L195–240) | no lot preserved | **[INHERIT]** preserve `lot_id` from the damage/repair-out quants so repaired stock returns to its original lot |
| G3 | `wms_barcode/wizards/scan_return*.py` + `stock_picking.py` returnable fields (~L107–131) | return placed, no explicit lot | **[INHERIT]** read the original issue picking's move-line `lot_id`; return to the **original lot** when known |

## H. Migration + tests + CI

| # | Where | Today | v20 |
|---|-------|-------|-----|
| H1 | `wms_barcode/migrations/19.0.1.7.0/pre-migration.py` (ALTER+UPDATE, idempotent, logged) | migration template | **[NEW]** legacy-lot migration in `wms_perishable/migrations/...` (see `03`) |
| H2 | test base (`TransactionCase`, `@tagged("post_install","-at_install","wms",...)`) e.g. `tests/test_returnable_items.py`, `test_damage_guard.py`; CI `--test-tags wms,...`; **0-skips guard** in `ci.yml` (~L279–289) | 69 test files today | **[NEW]** `WmsLotTestBase` fixture + 100+ tests, new tags `wms_perishable`, `wms_fefo`, `wms_recall`, `wms_migration_lot`; add tags to CI; **no `@skipIf`** (CI requires 0 skips) |
| H3 | `wms_reports/migrations/19.0.4.6.0/post-migration.py` (post-migration template) | post-migration template | model for the post step (backfill move-line lot) |

## I. Dependency to add

`product_expiry` (Odoo standard) — **not currently a dependency anywhere** (confirmed). Provides
`stock.lot.expiration_date`, `alert_date`, `removal_date`, and product `use_expiration_date` /
`expiration_time`. Add to `wms_perishable/__manifest__.py` `depends`. Do **not** hand-roll lot
expiry fields.

## Subsystem dependency graph (build order implied)

```
product_expiry (dep)
   └─ wms_perishable
        ├─ extends product.template ...... E (perishable kinds, auto-enable)
        ├─ extends stock.lot ............. lifecycle state, supplier meta
        ├─ extends stock.quant ........... A2 wms_effective_expiry  → A1 FEFO sort
        ├─ extends stock.location ........ B1 quarantine/recall flags → A3 exclusion
        ├─ extends scan_receipt .......... C (capture + lot create)
        ├─ extends scan_issue + approval . D (preview, expired block, bypass warn)
        ├─ extends damage/repair/return .. G (lot preserved)
        ├─ new wms.lot.recall ............ recall freeze + report
        ├─ new report views + dashboard .. F (per-lot)
        └─ migration + 100+ tests ........ H
```

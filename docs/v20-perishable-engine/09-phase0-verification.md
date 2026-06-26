# v20 Phase 0 — Codebase Verification Report (READ-ONLY)

> Produced by a 7-team parallel read-only investigation of the v19 codebase. No file/schema/DB was
> modified. Verifies the frozen spec (`07`) against real code. **Verdict: READY** — see §16.
> Line numbers are as-of v19 and will drift; re-anchor on symbols at implementation time.

## 1. Architecture verification — ✅
- 7 addons, clean layered dependency graph: `wms_location` (foundation) → `wms_fifo` → `wms_barcode`
  → `wms_repair_damage` / `wms_ai_forecast` → `wms_reports` → `wms_training`.
- Core models extended: `stock.location` (wms_location, wms_repair_damage, wms_reports), `stock.quant`
  (wms_location + wms_fifo), `stock.move.line`/`stock.picking` (wms_barcode), `product.template`/
  `product.product` (wms_location).
- **v20 can be a purely additive `wms_perishable` module via `_inherit`.** Two couplings to respect:
  - `stock.quant._gather` is **already overridden by wms_fifo** → v20 **must NOT override `_gather`**;
    it overrides the shared helper **`_wms_sorted_for_removal`** instead, which `_gather` calls via MRO
    (so the v20 sort is picked up automatically — no collision).
  - `product.template.create()/write()` are overridden by wms_location and call `super()`; v20's own
    `_inherit` overrides chain cleanly through MRO. **No edit to a frozen addon is required.**
- **Verdict:** additive extensibility confirmed; zero surgical edits needed.

## 2. Database verification — ✅ (with the known migration edge)
- All custom models, `_sql_constraints`/`models.Constraint`, unique constraints, and SQL-view models
  (wms_reports) mapped. Existing index: `idx_quant_fifo (product_id, in_date) WHERE quantity>0`.
- **No product is `tracking='lot'` today; all `stock.quant.lot_id` are NULL; `product_expiry` is NOT a
  dependency** anywhere. `wms_expiry_date` is a template field (index=True) driving today's FEFO + the
  expiry alert view.
- Lot tracking is **orthogonal** to the unique constraints (`default_code`, `wms_product_code`,
  barcode) — keep `lot_id` nullable; no constraint conflict. The stored-computed pattern (`wms_slot_id`)
  is the template for `wms_effective_expiry`.
- **Verdict:** schema ready; the only edge is flipping `tracking='lot'` on stock-on-hand (→ §5/§13).

## 3. Touch-point verification — ✅ (all 5 claims SUPPORTED)
Confirmed against code (file:line in `02-touch-point-map.md`):
1. `stock.quant._wms_sorted_for_removal` is the **single** removal-order method; `find_oldest_quants_for_product`
   **and** wms_fifo's `_gather` both delegate to it.
2. The planner `base_domain` excludes `wms_is_damage` / `wms_is_repair` (where quarantine/recall add 2 leaves).
3. `scan_receipt` carries `lot_id` per line → `stock.move.line.lot_id` at validate.
4. `scan_issue` has the manager-approval gate + persistent `wms.issue.approval` (reuse for expired override).
5. Current FEFO keys on the **template** `wms_expiry_date` (collapses to FIFO).
**The EXACT methods that change:** `_wms_sorted_for_removal` (sort key), `find_oldest_quants_for_product`
(domain), `scan_receipt.action_validate` (lot create), `scan_issue`+`wms.issue.approval` (expired reason).
**Nothing else in the removal path changes** — `_gather`, `action_plan`, `_build_issue_picking`,
reservation, and the locks are untouched.

## 4. Security verification — ✅ (one minor gap)
- Group hierarchy (manager / storekeeper / `group_wms_can_*` capabilities, implied_ids) + ACLs +
  the triple-defense approval gate (view group + ACL read+create-only for keepers + in-method
  `_ensure_can_decide`) all verified. `perm_unlink=0` makes audit rows append-only.
- **SUPPORTED:** add `group_wms_can_approve_perishable` implied into manager (pattern exists);
  immutable audit via `mail.thread` + `tracking=True` (for expiry-correction / recall / destroy /
  override).
- **GAP (PARTIAL):** **no `ir.rule` multi-company isolation** — relies on model-level company filtering.
  The gaushala is single-company, so practical risk is low, but v20 should add `ir.rule` records
  (`company_id` domain) on the new models for correctness. → Risk R-SEC1.

## 5. Migration verification — ✅
- 31 existing migration files follow an idempotent, logged pre/post pattern (e.g. wms_location
  19.0.3.2.0 de-dups SKUs before a UNIQUE constraint). CI runs the **prev-tag → HEAD upgrade path**
  (`ci.yml`, `PREV_TAG`, currently `v19.0.20.0.0` — must be bumped to the latest v19 release before
  the first v20 CI run).
- **Legacy-lot migration is feasible with no blocker:** `lot_id` is nullable until tracking is on, so
  a pre-migration can create per-product `LEGACY-<date>-<id>` lots and assign existing on-hand quants
  before enabling `tracking='lot'`; post-migration backfills `stock_move_line.lot_id`. Rollback =
  restore the pre-migration backup (`restore-native.ps1`).
- **Verdict:** GREEN. v20 writes `wms_perishable/migrations/20.0.1.0.0/{pre,post}-migration.py`.

## 6. Performance verification — ⚠️→✅ (the most important finding)
- **Real N+1 today:** `_wms_sorted_for_removal`'s FEFO lambda does `q.product_id.product_tmpl_id.wms_expiry_date`
  per quant inside `sorted()` — a per-quant ORM traversal. Adding `q.lot_id.expiration_date` would
  **double** it → a bulk FEFO sort (hundreds–thousands of quants) could take **1–3 s**, blowing the
  **<200 ms** target.
- **The design already mitigates this:** the spec/DB plan key the sort on a **stored, indexed
  `stock.quant.wms_effective_expiry`** (lot expiry → template fallback), NOT a lazy lambda. This is
  **mandatory, not optional** — confirm V20-008 implements it as `store=True, index=True` and the sort
  reads that single column. Add **`idx_quant_fefo (product_id, wms_effective_expiry, in_date, id)
  WHERE quantity>0`** (mirrors `idx_quant_fifo`).
- **Residual caveat:** the stored field's **recompute cascade** — editing a lot's expiry recomputes all
  that lot's quants. Bounded (few quants/lot; expiry edits are rare + manager-only), acceptable; keep
  the `@api.depends` tight (`lot_id.expiration_date`, `product_id.product_tmpl_id.wms_expiry_date`).
- Report views (expiry-alert, product-stock) gain a `stock_lot` join; manageable with the index.
- **Verdict:** targets achievable **iff** the sort uses the stored+indexed field. → Risk R-PERF1.

## 7. Testing verification — ⚠️ (YELLOW — infra to build)
- Convention solid: `TransactionCase` + `@tagged("post_install","-at_install","wms",<feature>)`; CI runs
  `--test-tags wms,...` with a **0-skips guard** (`@skipIf` is forbidden). ~69 test files / ~150 methods
  today; **no shared base class** exists.
- **v20 must add** `wms_perishable/tests/common.py::WmsPerishableCase` (tracked product, ~5 lots with
  varied expiry, warehouse + quarantine/recall locations, keeper, settings) and organize 100+ tests
  into ~15–20 files with `wms_perishable`/`wms_fefo`/`wms_recall`/… tags wired into CI. → V20-021.
- **Verdict:** design complete; building the base + tags is routine. YELLOW only because it's net-new work.

## 8. Risk register
| ID | Risk | Sev | Likelihood | Mitigation |
|----|------|-----|-----------|------------|
| R-PERF1 | Per-lot FEFO N+1 → misses <200 ms | High | High if naive | **Mandatory** stored+indexed `wms_effective_expiry` + `idx_quant_fefo`; sort reads the column, never a lambda traversal |
| R-PERF2 | `wms_effective_expiry` recompute cascade on lot-expiry edit | Med | Low (rare edits) | Tight `@api.depends`; expiry edits are manager-only + infrequent |
| R-MIG1 | `tracking='lot'` flip on live stock corrupts history | High | Med | 3 migration paths; auto-enable only on NEW products; backup-first; restore = rollback (§5/§13) |
| R-ARCH1 | Double-override of `_gather` (wms_fifo + v20) | High | Low (avoidable) | v20 overrides `_wms_sorted_for_removal` ONLY; never `_gather` |
| R-SEC1 | No `ir.rule` multi-company isolation | Low (single-company) | n/a | Add `ir.rule` (`company_id`) on new models |
| R-TEST1 | Skipped tests fail CI | Low | Low | No `@skipIf`; full-install fixtures in the base class |
| R-MIG2 | Stale CI `PREV_TAG` | Low | Med | Bump to latest v19 release before first v20 CI run |
| R-REG1 | FIFO regression for non-perishables | High | Low | The FIFO branch is untouched; regression tests assert it |

## 9. Implementation dependency graph
```
product_expiry (new dep)
  └─ wms_perishable
       ├─ product.template (_inherit): perishable kinds + auto-enable tracking + shelf-life policy
       ├─ stock.lot (_inherit): lifecycle state + supplier meta + expiration_date (product_expiry)
       ├─ stock.quant (_inherit): wms_effective_expiry (stored,indexed) ──┐
       ├─ override _wms_sorted_for_removal ◄───────────────────────────────┘ (keys on the column)
       │     └─ auto-consumed by find_oldest_quants_for_product + wms_fifo._gather (no edit)
       ├─ stock.location (_inherit): wms_is_quarantine / wms_is_recall ──► planner domain leaves
       ├─ scan_receipt (_inherit): batch/expiry/supplier + lot create + duplicate detection + auto-name
       ├─ scan_issue + wms.issue.approval (_inherit): expired block / bypass / preview / short-dated / reversal
       ├─ wms.lot.recall (new) ──► freeze + unreserve + exclusion
       ├─ reports (_inherit/new): re-key expiry-alert; lot timeline
       ├─ security: group_wms_can_approve_perishable + ir.rule(company)
       ├─ migration 20.0.1.0.0 (pre/post): legacy-lot
       └─ tests/common.py + 100+ tests
```

## 10. Recommended implementation order
P0 scaffold → P1 lot+receipt(+duplicate+auto-name+shelf-life) → P2 FEFO (stored field + sort + index)
→ P3 issue safety (block/bypass/preview/short-dated/reversal) → P4 recall+quarantine exclusion +
unreserve + lot-lock → P5 reports + lot barcode + timeline → P6 migration → P7 hardening (100+ tests,
browser, sim, CI). Each phase green before the next. (Matches `04`; the only sequencing note from
Phase 0: build the stored `wms_effective_expiry` in P2 **before** wiring the sort.)

## 11. Files that WILL change (all via new `wms_perishable` `_inherit`/new — NOT edits to frozen addons)
New module `wms_perishable/`: `models/{product_template,stock_lot,stock_quant,stock_location,
stock_picking}.py` (inherits), `wizards/{scan_receipt,scan_issue}.py` (inherits), `models/
wms_lot_recall.py` + `wms_perishable_settings.py` (new), `models/<reports>.py` (re-key/new views),
`security/{groups,ir.model.access.csv,ir_rule}.xml`, `data/{sequences,cron,settings}.xml`,
`views/*`, `migrations/20.0.1.0.0/{pre,post}-migration.py`, `tests/common.py` + `tests/test_*.py`,
`hooks.py` (post-init: locations + `idx_quant_fefo`), `__manifest__.py`.

## 12. Files that MUST NOT change (frozen v19 — verified no edit required)
All existing addon code: `wms_location/*`, `wms_fifo/*`, `wms_barcode/*`, `wms_repair_damage/*`,
`wms_ai_forecast/*`, `wms_reports/*`, `wms_training/*`. In particular **do not touch**
`wms_location/models/stock_quant.py`, `.../stock_location.py`, `.../product_template.py`,
`wms_fifo/models/stock_quant.py`, `wms_barcode/wizards/scan_*.py` — v20 extends them by inheritance.
(If a genuinely missing hook ever forces a 1-line surgical edit, it is its own commit with a note —
none is currently required.)

## 13. Expected migration impact
Net-new objects only (a module, fields, 1–2 indexes, locations, sequences). On a **fresh/zero-stock DB
the impact is nil**. On a populated DB, the legacy-lot migration touches every on-hand `stock.quant`
of perishable products once (create legacy lot + set `lot_id`) + backfills `stock_move_line.lot_id` —
measured + reported, backup-first, restore = rollback. No destructive change to existing data.

## 14. Expected regression impact
**Low, bounded.** The FIFO branch of `_wms_sorted_for_removal` is unchanged → non-perishables behave
identically. `_gather`, the planner's picking build, reservation, and the approval flow are untouched.
The risks are (a) the stored `wms_effective_expiry` recompute (perf, not correctness) and (b) the
report-view re-key (covered by tests). The 0-skips full-suite + the prev-tag upgrade job catch
regressions in CI.

## 15. Estimated complexity
**Moderate.** No new architecture; the FEFO change is one method keyed on one stored column; the
exclusion/recall/quarantine reuse the damage/repair pattern; the approval gate is reused; lots already
propagate at receipt. Real effort is breadth (many small inherited pieces), the migration on populated
DBs, the issue-safety UX, and 100+ tests. Wave 1 ≈ 18–22 dev-days (per `04`).

## Spec-requirement verification matrix (nothing UNKNOWN)
| Spec area (07 §) | Status | Note |
|---|---|---|
| Lot barcode/label (2.5), timeline (2.6), auto-naming (2.7) | **SUPPORTED** | `resolve()` maps barcode→lot; move-line history; ir.sequence pattern |
| Lot lifecycle states (2.2) | PARTIAL | new field on stock.lot; additive |
| Shelf-life policy (2.8) | PARTIAL | extends `KIND_DEFAULT_MIN_LIFE_DAYS`; per-product min-receive/min-issue new |
| Receipt batch/expiry/supplier (3.1) | PARTIAL | `lot_id` per line exists; new fields + lot create |
| Duplicate detection (3.6), near-expiry guard (3.7) | NOT-yet (additive) | new logic at receipt; no blocker |
| FEFO order (4.1) | PARTIAL | engine exists; change the 1 sort key to the stored column |
| Auto-split (4.2), FEFO reservation (4.6) | **SUPPORTED** | planner returns multi-lot plan; `_gather` delegates to the sort |
| Exclusions / quarantine / recall (4.3, 5, 6) | PARTIAL | reuse `wms_is_damage/repair` domain pattern + new `wms.lot.recall` |
| Lot lock (4.7) | PARTIAL | `FOR UPDATE` locks exist; extend to lot |
| Expired block + override (7.1), bypass (7.2), short-dated (7.3) | PARTIAL | reuse approval gate; add `reason_expired` |
| Preview/availability summary (7.4) | PARTIAL | plan preview exists; add balances + explanation |
| Disposal (8) | NOT-yet (W2, additive) | new manager action |
| Corrections / lot-aware reversal / returns (9) | PARTIAL | reversal exists; make lot-aware |
| Permissions (11) | **SUPPORTED** | group pattern exists; multi-company `ir.rule` = the only PARTIAL |
| Audit immutability | **SUPPORTED** | mail.thread + tracking + `perm_unlink=0` |
| Reports/alerts (12) | PARTIAL | re-key expiry-alert view + digest |
| Migration (13) | **SUPPORTED** | pattern + legacy-lot feasible |
| Extension hooks (16) | NOT-yet (additive) | attach points identified (Team C) |
**No requirement is UNKNOWN.** Every one is SUPPORTED, PARTIAL (infra exists, extend), or
NOT-yet-but-additive (new code, attach point identified, no blocker).

## 16. Implementation Readiness Report — ✅ READY
Every Phase-0 acceptance criterion is met:
- **Every dependency identified** (§1, §9) · **every touch point mapped** (§3, `02`) · **every
  migration path verified** (§5) · **every risk documented** (§8) · **no unknown architecture** ·
  **no hidden coupling** (the only ones — `_gather`, create/write — are understood and handled by MRO)
  · **no missing dependencies** (add `product_expiry`) · **no unexplained overrides** (all catalogued)
  · **complete implementation roadmap confirmed** (`04` + §10).
- **Conditions to honor when building:** (1) FEFO sort MUST read the stored+indexed `wms_effective_expiry`
  (R-PERF1); (2) auto-enable `tracking='lot'` only on NEW products, migrate existing via the legacy-lot
  path (R-MIG1); (3) override `_wms_sorted_for_removal`, never `_gather` (R-ARCH1); (4) add the
  `WmsLotTestBase` + 0-skip tags (R-TEST1); (5) add `ir.rule` company isolation (R-SEC1); (6) bump CI
  `PREV_TAG` (R-MIG2).

**Verdict: the v19 codebase is fully understood and structurally ready for v20 Wave 1.** Implementation
may begin once — and only once — (a) v19 is certified & frozen and (b) the `v20` branch is cut. Then run
[`08-implementation-prompt.md`](08-implementation-prompt.md).

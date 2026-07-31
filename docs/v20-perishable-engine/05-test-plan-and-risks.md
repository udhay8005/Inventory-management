# v20 Test Plan + Risk Register

## 1. Test infrastructure (reuse the existing pattern)

- `TransactionCase`, decorated `@tagged("post_install","-at_install","wms", "<area>")` — same as
  every existing WMS test (e.g. `test_returnable_items.py`, `test_damage_guard.py`).
- New shared fixture `wms_perishable/tests/base.py` → `WmsLotTestBase`: a warehouse, a keeper,
  a tracked perishable product + a non-perishable control, Quarantine/Recall/Damage/Repair
  locations, and helpers `_lot(product, expiry)`, `_quant(product, loc, qty, lot)`,
  `_receive(...)`, `_issue(...)`.
- New tags: `wms_perishable`, `wms_fefo`, `wms_recall`, `wms_quarantine`, `wms_migration_lot`.
  **Add them to CI** (`ci.yml` `--test-tags`). **No `@skipIf`** — CI enforces 0 skips.
- CI already runs fresh-install + upgrade + smoke + lint + security; the migration must pass the
  upgrade job, and the legacy-lot path needs its own upgrade-from-tag test.

## 2. Coverage matrix (target 100+ tests)

| Area | ~Count | Key cases |
|------|--------|-----------|
| Receipt + lots | 12 | one lot; 3 receipts → 3 lots (no merge); batch+expiry captured; same supplier/expiry still separate lots; tracking-guard error; legacy non-lot receipt unchanged |
| FEFO ordering | 15 | earliest-expiry first; auto-split across lots (need 250 → 100/75/75); expiry tie → in_date; per-lot beats template; **non-perishable stays FIFO (regression)**; quarantine/recalled excluded |
| Issue safety | 15 | expired → blocked; manager override + audit reason; bypass-FEFO warn + confirm; preview shows lots + resulting balances; gate-off bypass; high-value/min-life still work (regression) |
| Partial / split | 8 | issue 5 of 50kg → 45 same lot; issue 35 of 100 → 65 same lot; no new lot created |
| Damage / repair | 12 | damage 12 of 100 → 88 same lot, history kept; >1 lot on slot → error; repair returns to original lot; scrap with lot |
| Return | 10 | return to original lot when known; return when lot unknown → floor; overdue-return report by lot |
| Recall | 10 | flag lot → frozen (excluded from picker); locate everywhere; full receipt+issue history; resolve/dispose; manager alert |
| Quarantine | 8 | receive→quarantine (excluded); approve→pickable; reject→recalled/destroyed |
| Reports / alerts | 10 | per-lot expiry tiers (180/90/60/30/15/7/expired); value-at-risk; digest per-batch; ledger sort; traceability join; 2 self-diagnostics probes |
| Migration | 12 | legacy lot created per product; quants assigned; move-line backfill; idempotent re-run; upgrade-from-tag; rollback-by-restore documented |
| Dashboard / search | 6 | dashboard counts; search by lot/batch/supplier/expiry |
| Concurrency / edge | 8 | concurrent issue on same lot (lock holds); duplicate active recall blocked; null expiry handling; tz-safe days-to-expiry |

## 3. Self-heal loop (the project's standing rule)
lint → static analysis → unit → integration → browser automation → warehouse simulation →
performance → regression → fix → repeat — until: all tests pass, CI green, no regressions, no
lint errors, no dead code, no TODO/FIXME, no failing browser tests. Every phase gate in
[`04`](04-implementation-plan-and-backlog.md) is one turn of this loop.

## 4. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | `tracking='lot'` on live stock breaks Odoo / orphans history | Med | High | Migration §5 — fresh DB / zero-stock / legacy-lot; backup-first; restore = rollback. Auto-enable only on NEW products. |
| R2 | FEFO override misses a removal path | Low | High | Only one chokepoint (`_wms_sorted_for_removal`); `_gather` + planner both delegate. Regression tests assert FIFO unchanged for non-perishables. |
| R3 | Per-lot sort slows large issues | Med | Med | Stored indexed `wms_effective_expiry` + `idx_quant_fefo`; performance test in the loop. |
| R4 | Inherit-overrides couple to v19 internals that drift | Med | Med | Localised overrides; if a needed hook is missing, one **[SURGICAL]** v19 edit as its own commit. Pin line-number checks to symbols, not numbers. |
| R5 | `product_expiry` interaction (its native FEFO strategy vs WMS engine) | Low | Med | Use `product_expiry` for lot *fields only*; keep the WMS engine as the sole picker; assert the removal strategy isn't double-applied. |
| R6 | Expired-block too aggressive (blocks legitimate emergency vet use) | Med | Med | Block → manager-approval override with audit reason (not a hard wall); configurable via settings. |
| R7 | Multiple lots on one slot makes damage/return ambiguous | Med | Med | Error + ask the keeper to damage/return *by lot*; one-lot-per-slot is the norm. |
| R8 | Recall race (lot picked while being recalled) | Low | Med | Freeze sets lot state + picker domain excludes it; lock on the lot; archive table for history. |
| R9 | Scope creep into AI/QR/voice/IoT | Med | Med | Hard rule: build nothing speculative unless users ask; Wave 2 gated on real-use feedback. |
| R10 | Skips sneak into CI | Low | Med | The 0-skips guard already fails CI; no `@skipIf` in new tests. |

## 5. Acceptance / production-readiness gate
Feature complete only when: all functionality implemented; full automated suite passes; browser
validation passes; warehouse simulation passes; no regressions; CI green; docs updated; final
production-readiness report generated — with **no fabricated PASS results** (every claim verified
by execution). Wave 1 and Wave 2 each pass this gate independently; Wave 2 starts only after 2–4
weeks of real Wave-1 use.

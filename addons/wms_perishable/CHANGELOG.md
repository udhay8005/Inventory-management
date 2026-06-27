# Changelog — wms_perishable (v20 Universal Perishable Engine)

## 19.0.1.20.0 — Wave 1 completion: V20-022 per-kind shelf-life policy — 2026-06-27

Implements the per-kind shelf-life table from functional spec §2.8 (previously
deferred at sign-off; re-included by owner decision 2026-06-27). Additive only.

### Added

- **V20-022** Per-kind shelf-life policy (`wms.shelf.life.policy`): an
  admin-editable table of total / min-at-receipt / min-at-issue days per WMS
  kind, seeded with the spec defaults (vaccine 180/120/30, medicine 730/180/60,
  feed 90/30/7, chemical 365/90/30, and 0/60/30 for fluid/food/supplement/
  fertilizer/pooja).
- Per-product overrides on the product form (`wms_shelf_life_days`,
  `wms_min_receive_life_days`, `wms_min_issue_life_days`) — distinct from the v19
  `wms_min_life_days` (re-request interval). Resolver precedence:
  per-product override > per-kind policy > global fallback.
- The near-expiry **receipt** guard now uses the per-product/per-kind minimum
  (was a single global 60-day floor); manager override unchanged.
- New short-dated-at-**issue** guard: the FEFO plan flags near-expiry (not yet
  expired) stock below the kind's min-issue shelf life and blocks the issue
  unless a Manager approves it (audited on the usage note).
- Global fallback **Shelf-life Settings** (WMS ▸ Configuration), stored as
  `ir.config_parameter` (`wms_perishable.min_receive_shelf_life_days` default 60,
  `wms_perishable.min_issue_shelf_life_days` default 0).
- Security ACLs (manager RWCD / user R) for the policy table; 8 new tests
  (`test_shelf_life_policy.py`). `wms_perishable` suite: 74 tests, 0 failed.

## 19.0.1.19.0 — Wave 1 (pilot build `v20.0.0-beta1`) — 2026-06-26

First implemented release. Additive over the frozen v19 addons — no v19 file is
edited; everything is an `_inherit` extension or a new model. Built against the
frozen design in [`../../docs/v20-perishable-engine/`](../../docs/v20-perishable-engine/)
(owner sign-off 2026-06-24). Full WMS suite: 519 tests, 0 failed / 0 skipped;
CI green on every commit; independent 6-team audit GREEN.

### Added

- **V20-002** New perishable kinds: vaccine, supplement, chemical, fertilizer, food.
- **V20-003** Perishables auto lot + expiry tracked on creation (both create paths).
- **V20-004/005** Lot-aware Scan Receipt: batch / expiry / supplier capture;
  find-or-create lot (never merges distinct batches); auto-named lots.
- **V20-007** `stock.lot` lifecycle (available / quarantine / recalled / destroyed)
  + supplier / batch / invoice / manufacture metadata + computed expired flag.
- **V20-008** Stored + indexed `stock.quant.wms_effective_expiry` (+ `idx_quant_fefo`).
- **V20-009** Per-lot FEFO removal (overrides `_wms_sorted_for_removal` only) + auto-split.
- **V20-010** Per-lot expiry / batch / resulting-balance on the Scan Issue plan.
- **V20-011a** Expired stock blocked from issue + shortfall reason.
- **V20-011b** Manager override to issue expired (audited).
- **V20-011c** Disposal carve-out — expired stock stays damageable.
- **V20-012** Lot-aware issue reversal — restores the original lot.
- **V20-013** Lot recall: freeze + cancel reservations + exclude + release.
- **V20-014** Lot quarantine: hold / release / reject / destroy.
- **V20-015** Per-lot expiry report (owner thresholds 180/90/60/30/15/7/expired).
- **V20-016** Lot barcode label — print + scan-back.
- **V20-017** Lot timeline + lifecycle on the lot form.
- **V20-018** Near-expiry receiving guard with manager override.
- **V20-019** Stable extension hook API — v20 Hook API 1.0.
- **V20-020** Perishable lot-tracking migration wizard (zero-stock flip + legacy-lot).
- **V20-021** Warehouse-simulation + scaled-FEFO hardening tests.

### Operational notes

- Migration rollback is by **restoring the pre-migration backup** (Odoo cannot
  cleanly downgrade `tracking='lot'` once stock carries lots) — back up first.
- `wms_perishable.min_receive_shelf_life_days` (default 60) configures the
  near-expiry receiving guard; 0 disables it.

### Out of Wave-1 scope (deferred)

- V20-022 per-kind shelf-life table; V20-023 lot lock during edits; V20-006
  duplicate-lot manager dialog (core dedup is in V20-005); all Wave-2
  analytics / dashboards / forecasting / cold-chain.

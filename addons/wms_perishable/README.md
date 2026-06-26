# wms_perishable — Universal Perishable Engine (v20 Wave 1)

> **STATUS: SCAFFOLD ONLY.** Folder layout, manifest, test base, and CI wiring
> are in place. **No features are implemented yet.** This is the official
> starting point for Wave 1.

This additive module brings **per-lot expiry tracking + FEFO + quarantine/recall**
to the gaushala WMS, **without editing the frozen v19 addons**. It `_inherit`-extends
the v19 models/wizards (the single FEFO chokepoint
`stock.quant._wms_sorted_for_removal`, the Scan Receipt lot-capture, the Scan
Issue approval gate for expired-issue blocking) and owns the genuinely new
models (lot lifecycle, `wms.lot.recall`, quarantine, settings, per-lot reports,
dashboard).

## Build from the frozen spec

Everything is designed and frozen in [`../../docs/v20-perishable-engine/`](../../docs/v20-perishable-engine/):

- `01-architecture.md` — the additive design + the single FEFO override.
- `03-database-and-migration.md` — new models/fields/indexes, the
  `wms_effective_expiry` stored+indexed field, the legacy-lot migration.
- `04-implementation-plan-and-backlog.md` — Wave 1 tickets (V20-001…019).
- `05-test-plan-and-risks.md` — the test breakdown (built on `tests/common.py`).
- `07-functional-specification.md` — **the frozen contract** (owner sign-off 2026-06-24).
- `08-implementation-prompt.md` — the Wave 1 kickoff prompt.
- `09-phase0-verification.md` — the 6 build conditions (READY verdict).

## Wave 1 build conditions (carried from Phase-0)

1. FEFO sort MUST read the **stored+indexed** `stock.quant.wms_effective_expiry`
   (lot→template fallback) + `idx_quant_fefo` — never a per-quant lambda traversal.
2. Auto-enable `tracking='lot'` on **new** products only; migrate existing via the
   legacy-lot path at zero stock / go-live.
3. Override `_wms_sorted_for_removal` **only**, never `_gather` (wms_fifo already
   overrides `_gather`; the MRO picks up the v20 sort).
4. Build on the `WmsLotTestBase` here + 0-skip tags.
5. Add `ir.rule` company isolation (none exists in v19 — single-company today).
6. Keep the CI `PREV_TAG` at the last green release before each v20 CI run.

## Layout

```
wms_perishable/
  __manifest__.py        depends: v19 addons + product_expiry
  models/                FEFO override, lot lifecycle, recall, quarantine, settings
  wizards/               (Wave 1 wizards)
  views/                 (Wave 1 views/dashboard)
  security/              ir.model.access.csv + ir.rule (build condition 5)
  data/                  shelf-life table, alert thresholds, cron
  tests/  common.py      WmsLotTestBase (the shared seam) + scaffold smoke test
```

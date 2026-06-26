# v20 — Universal Perishable Inventory Engine — Implementation Package

> **Status:** WAVE 1 IMPLEMENTED — pilot-ready (`v20.0.0-beta1`). All Wave-1 tickets
> (V20-001…021) are implemented in the additive `addons/wms_perishable` module, full
> WMS suite green (519 tests, 0 failed/skipped), CI green on every commit (lint,
> security scan, module tests, v19→HEAD upgrade path, native smoke), and an
> independent 6-team read-only audit (architecture / security / performance / QA /
> docs / devops) returned GREEN with zero blocking defects.
>
> The roadmap from here is the human-run **warehouse pilot** (2–4 weeks) on the
> beta1 build, then verified fixes → `v20.0.0-rc1`, then owner approval →
> `v20 → main` → `v20.0.0` production. Wave 2 follows the pilot. The documents
> below are the frozen design this implementation was built against.

This package exists so that, the day after v19 go-live sign-off, implementation can
start on a fresh `v20` branch with minimal planning delay. Everything below is grounded
in a touch-point-by-touch-point read of the current (v19) codebase.

## The documents

| File | What it gives the implementer |
|------|-------------------------------|
| [`01-architecture.md`](01-architecture.md) | The design: the additive `wms_perishable` module, the data model (lot lifecycle, recall, quarantine, settings), the single FEFO chokepoint, the universal perishable-kinds, and the end-to-end flows. |
| [`02-touch-point-map.md`](02-touch-point-map.md) | Every file:line the engine touches, by subsystem, marked *inherit/extend* vs *new*. The dependency map. |
| [`03-database-and-migration.md`](03-database-and-migration.md) | New models, fields, indexes, location flags, the `product_expiry` dependency, and the legacy-lot migration + rollback. |
| [`04-implementation-plan-and-backlog.md`](04-implementation-plan-and-backlog.md) | Wave 1 (MVP) and Wave 2 phase-by-phase, then an ordered, ticket-level backlog with effort tags. |
| [`05-test-plan-and-risks.md`](05-test-plan-and-risks.md) | The 100+ test breakdown (areas, tags, base class, CI wiring) and the risk register. |
| [`06-operational-gap-analysis.md`](06-operational-gap-analysis.md) | Every real warehouse scenario stress-tested against the design; surfaces 8 new requirements + 7 owner policy decisions. |
| [`07-functional-specification.md`](07-functional-specification.md) | **The contract** (DRAFT, pending owner approval). Lot lifecycle, FEFO/FIFO, quarantine, recall, approval, policies, permissions, reports, dashboards, alerts, migration. Freeze on approval. |
| [`08-implementation-prompt.md`](08-implementation-prompt.md) | The Wave-1 kickoff prompt — **gated**: do not run until (1) spec approved, (2) v19 certified & frozen, (3) v20 branch cut. |
| [`09-phase0-verification.md`](09-phase0-verification.md) | Read-only codebase verification (7-team) against the frozen spec: 15 deliverables + spec-requirement matrix + **Implementation Readiness Report (✅ READY)**, with 6 build conditions. |

## Design stage status

Design is **COMPLETE and the specification is FROZEN** — owner sign-off **2026-06-24**, all 9
decisions at their recommended defaults ([`07` §Owner sign-off](07-functional-specification.md)).
The gap analysis ([`06`](06-operational-gap-analysis.md)) confirmed the architecture holds and
surfaced 10 reuse-based requirements (folded into the spec). **Implementation has NOT started — it
is gated on (a) v19 certified & frozen and (b) the v20 branch being cut; then run
[`08`](08-implementation-prompt.md).**
The owner's refinements (2026-06-24, multiple rounds) are incorporated: batch-uniqueness key
(company, product, batch, expiry); recommended manufacture-date capture; **per-product shelf-life
policy** (min-receive + min-issue per kind, replacing the global 60-day); near-expiry receiving
guard + short-dated-issue guard; **FEFO reservation** (already structural — `_gather` FEFO-orders)
+ **lot lock during edits**; automatic lot naming; supplier-recall mode + notice number;
RECALL-ACTIVE visibility; lot-label content; FEFO explanation in the preview; and **versioned,
stable extension hooks** (`v20 Hook API 1.0` — receipt/issue/recall/quarantine/disposal, spec §16)
so future modules never touch the core FEFO engine. Wave 2 gains an **Expiry Risk Engine** (consumption
vs shelf-life, wired to `wms_ai_forecast`), Stock Health Score, expiry calendar, supplier-performance
analytics, lot audit score, and bulk lot operations.

The owner **tightened the wave split (2026-06-24):** Wave 1 = inventory-correctness + safety only
(now including recall-freeze, quarantine exclusion, and unreserve-on-freeze), plus three
owner-added Wave-1 features — **duplicate-lot detection, per-lot barcode, lot timeline**; all
dashboards / analytics / advanced lifecycle / cold-chain / cycle-count move to Wave 2. See
[`04`](04-implementation-plan-and-backlog.md).

**Do not start implementation until: (a) the spec is approved & frozen, and (b) v19 is certified,
tagged, and frozen, and (c) the v20 branch is cut.**

## Executive summary

**Goal.** One **Universal Perishable Engine** keyed on **Lot/Batch** records, governing every
expiry-sensitive category (medicine, vaccine, feed, supplement, chemical, fertilizer, food,
fluid, pooja, and any future one). Non-perishables keep today's plain FIFO, untouched.

**Core principle.** ONE product → MANY lots. Never separate products per batch; never merge
lots. Partial issue / damage / return keeps the *same* lot. FEFO (earliest-expiry-first) for
perishables; FIFO for the rest. Complete lot traceability.

**Why it's a moderate, not heroic, build.** The v19 codebase is already shaped for this:

- Removal order is centralised in **one method** — `stock.quant._wms_sorted_for_removal`
  (`wms_location`) — which the Scan Issue planner (`find_oldest_quants_for_product`) and Odoo's
  `_gather` both delegate to. **FEFO is one override.**
- The Scan Receipt wizard already carries a `lot_id` per line and propagates it to move lines.
- The picker already **excludes** Damage / Repair-Out locations via a `wms_is_*` boolean
  pattern — Quarantine and Recall reuse it exactly.
- The Scan Issue wizard already has a **manager-approval gate** (high-value / min-life) with a
  persistent approval model — the expired-issue override reuses it.
- The Expiry-Alert report + weekly digest already exist (keyed on the template date) — re-key
  to per-lot.

**Architecture headline.** v20 ships as a **new additive `wms_perishable` module** that uses
Odoo `_inherit` to extend the existing models/wizards/views and owns the genuinely new models
(lot lifecycle, recall, quarantine, settings, dashboards, per-lot reports). **The frozen v19
addons are not edited.**

**The one sharp edge.** Switching a product to `tracking='lot'` while it holds stock is
disruptive in Odoo. Do it on a fresh DB / at go-live, or per-product at zero stock, or via the
legacy-lot migration in [`03`](03-database-and-migration.md). Never flip tracking on live
non-zero stock without one of those.

## Definition of Done (carried from the project's hard rules)

The feature is complete only when: all functionality implemented; all automated tests pass;
browser validation passes; warehouse simulation passes; no regressions; CI green; docs updated;
and a final production-readiness report is generated. No fabricated PASS results — every claim
verified by execution. Reuse before creating; no duplicate business logic; no unrelated
refactoring; no breaking API changes; no schema changes outside this feature; small,
logically-separated commits; every phase ends green before the next begins.

# v20 Functional Specification — the Contract

> **STATUS: ✅ APPROVED & FROZEN — owner sign-off 2026-06-24.** This is the frozen requirements
> contract: **no new features until v20 is complete** (change control, §15). All 9 OWNER decisions
> are confirmed at their recommended defaults (see sign-off below). **Implementation is still
> gated** on v19 certification + a v20 branch — see [`08-implementation-prompt.md`](08-implementation-prompt.md).
> Incorporates [`06`](06-operational-gap-analysis.md) + the owner's refinement rounds. The
> **[OWNER-n]** tags now record the *frozen* decision, not an open question.

## 1. Scope
A Universal Perishable Engine for every expiry-sensitive kind — medicine, vaccine, feed,
supplement, chemical, fertilizer, food, fluid, pooja, and any future one (`EXPIRY_SENSITIVE_KINDS`).
Non-perishables keep plain FIFO. Principle: **one product, many lots; never separate products per
batch; never merge lots.**

## 2. Lot model & lifecycle
2.1 A lot (`stock.lot`) belongs to one product and carries: batch number (= lot name), **expiry
date**, **manufacture date**, supplier, supplier batch, supplier invoice.
2.2 States (`wms_lot_state`): **available**(default) / **quarantine** / **recalled** /
**destroyed**. Not "reserved" (native `reserved_quantity`); not "expired" (computed).
2.3 Transitions are audited (actor + timestamp + reason) in the lot chatter.
2.4 History is **never deleted**; zero-qty lots are archived, not purged.
2.5 **Lot barcode & label.** Every lot has its own barcode; scanning it surfaces product, batch,
expiry, location(s), remaining qty. The label prints **product name, batch, expiry, manufacture
date, supplier, barcode/QR**. *(Wave 1.)*
2.6 **Lot timeline.** Complete per-lot history (supplier→receipt→putaway→transfer→issue→return→
damage→recall→destroy) from `stock.move.line`. Basic view **W1**; polished visual **W2**.
2.7 **Automatic lot naming.** If the supplier batch is blank, the system generates a lot name
`LOT-YYYY-NNNNNN` from a sequence — keepers never invent names. *(Wave 1.)*
2.8 **Shelf-life policy (per kind, overridable per product).** Each perishable kind defines
**total shelf life**, **minimum life at receipt**, and **minimum remaining life at issue** — a
single global threshold is *not* used. Default table **[OWNER-9]** (confirm / extend):
| Kind | Total | Min @receipt | Min @issue |
|------|------:|------:|------:|
| Vaccine | 180 d | 120 d | 30 d |
| Medicine | 730 d | 180 d | 60 d |
| Feed | 90 d | 30 d | 7 d |
| Chemical | 365 d | 90 d | 30 d |
| Fluid / Food / Supplement / Fertilizer / Pooja | per product | 60 d | 30 d |
Reuses the existing `KIND_DEFAULT_MIN_LIFE_DAYS` pattern; a product may override its kind's values.

## 3. Receipt rules
3.1 A perishable receipt requires per line **batch number** + **expiry date**; **manufacture date
recommended**; supplier/batch/invoice optional. Non-perishables unchanged.
3.2 The system **finds or creates** a lot; **never auto-merges** two distinct receipts.
3.3 Multiple receipts → multiple lots (Mon→A, Wed→B, Fri→C).
3.4 Perishable products are created `tracking='lot'` + `use_expiration_date`.
3.5 **[OWNER-4]** Inbound QC default **OFF**; when on, received stock lands in Quarantine until
approved (§5).
3.6 **Duplicate-lot detection.** Uniqueness key = **(company, product, batch, expiry)** — and,
**[OWNER-8]**, optionally supplier (batch alone is not the key: suppliers reuse batch numbers). On
a match: **add to existing** / **cancel** / **create new** (manager-only, **[OWNER-5]**).
3.7 **Near-expiry receiving guard.** If an incoming lot's remaining life is below the product's
**minimum life at receipt** (§2.8), **warn + manager approval** (audited); an optional per-kind
**reject** mode may be enabled. **[OWNER-9]**.

## 4. Removal, reservation & concurrency — FEFO / FIFO
4.1 Perishables: **earliest expiry first** (FEFO), tie-break oldest `in_date`, then `id`.
Non-perishables: FIFO. One ordering method, shared by Scan Issue and reservation.
4.2 The system **chooses** the lot(s); keepers don't free-pick; issues **auto-split** across lots.
4.3 **Excluded:** Damage / Repair-Out / **Quarantine** / **Recalled** locations, and any lot in
state quarantine/recalled/destroyed. Expired lots are excluded from the auto plan (override §7).
4.4 **Shortfall:** show planned vs shortage, with excluded qty by reason (expired/quarantined/
recalled). **[OWNER-3]** default: allow the partial issue + record the shortage.
4.5 **Concurrency:** the plan locks the product **and lot** (`FOR UPDATE`).
4.6 **FEFO reservation.** Reservations follow FEFO **automatically** — Odoo's `_gather` is
overridden to the same removal order, so a request reserves the **earliest-expiry** lot and holds
it; another keeper cannot grab a different lot before issue.
4.7 **Lot lock during edits.** While a manager edits a lot's **expiry / recall / quarantine**, the
lot is locked so no concurrent transaction issues from it.

## 5. Quarantine rules
5.1 Quarantine = a per-warehouse internal location (`wms_is_quarantine`), **excluded** from
removal; lots there are state `quarantine`. 5.2 Entry: inbound QC (§3.5) **or** a manager
**hold-an-existing-lot** action (defect, **cold-chain breach** [OWNER-4], vet flag). 5.3 Exit:
**approve** → storage (available) or **reject** → recalled/destroyed. 5.4 Reason mandatory + audited.

## 6. Recall rules
6.1 A recall (`wms.lot.recall`) sets the lot **recalled** and **freezes** it (excluded; **open
reservations cancelled**). Stores: lot, **mode (manual / supplier)**, supplier, **supplier
reference**, **recall notice number**, **recall date**, **reason** (supplier/quality/regulatory),
description. 6.2 The recall view shows current locations + remaining, full receipt + issue history,
and **affected downstream transactions** (**[OWNER-1]** department-level). 6.3 Managers notified;
resolve = resolved / disposed; one active recall per lot. 6.4 **Visibility:** **🔴 RECALL ACTIVE**
shown on lot / product / issue wizard / reports. *(Wave 1.)*

## 7. Issue safety — expired, bypass, short-dated, preview
7.1 Issuing an **expired** lot is **blocked**; proceeds only via **manager approval** + audit
reason (reuses the existing gate; adds `reason_expired`; re-checks at approve time).
7.2 **FEFO bypass** (a later-expiry lot while an earlier has stock) → **warn + confirm**; skipping
an earlier-expiry lot routes through manager approval (audited).
7.3 **Short-dated issue.** If the FEFO-selected lot's remaining life is below the product's
**minimum life at issue** (§2.8), **warn** the keeper — and **[OWNER]** optionally require manager
approval. Softer than the expired block.
7.4 **Pre-commit preview / lot-availability summary.** Before commit, the wizard shows **all
available lots** (expiry + qty), the **auto-selected** FEFO plan (take per lot), the **resulting
balances**, and **why each lot was chosen** ("earliest expiry 12-Jan-2027" — a training aid).
Nothing commits until **Confirm**. The manager-approval screen for large issues shows the same
**FEFO simulation** (consume plan + remaining) before approve.

## 8. Disposal / destruction  *(W2 workflow; expired stock is already safe in W1 — blocked + flagged)*
8.1 Manager **Dispose**: → disposal location/scrap, state **destroyed**, **value write-off**, logs
reason+qty+approver; history retained; feeds wastage analytics. 8.2 **[OWNER-6]**
`auto-quarantine-expired` default **OFF**.

## 9. Corrections & returns
9.1 **Correct lot expiry** — manager-only, audited (re-evaluates FEFO + alerts) **[OWNER-5]**.
9.2 **Wrong lot issued** — reversal is **lot-aware** (returns to the original lot). 9.3 **Returns**
— **[OWNER-2]** cold-chain kinds → Quarantine for QC; shelf-stable → original lot.

## 10. Inventory policies
No merge ever · split = same lot · damage keeps the lot + history (>1 lot/slot ⇒ act by lot) ·
adjustments/cycle-counts per lot · transfers preserve the lot · track tablets/units only (pack-size
is a label; whole-strip via `units_per_scan`).

## 11. User permissions (capability matrix)
| Action | Keeper | Manager |
|--------|:---:|:---:|
| Receive + capture batch/expiry/mfg | ✅ (capability) | ✅ |
| Issue (FEFO auto) | ✅ | ✅ |
| Confirm FEFO bypass (non-skipping) / short-dated warn | ✅ | ✅ |
| Override expired / skip earlier-expiry / receive near-expiry | ❌ (request) | ✅ approve |
| Create-new-lot despite duplicate / correct expiry / quarantine / recall / dispose | ❌ | ✅ |
| Bulk lot operations (W2) | ❌ | ✅ |
| View per-lot reports / timeline / dashboard | ✅ read | ✅ |
New group `group_wms_can_approve_perishable` implied into `group_wms_manager`.

## 12. Reports, dashboards, alerts
12.1 **Reports:** per-lot Expiry Alert (recall-aware) **[W1]**; Lot Timeline (basic) **[W1]**; Lot
Ledger **[W2]**; Lot Traceability **[W2]**; Recall report **[W2]**; Destroyed/Wastage **[W2]**;
**Expiry Calendar** (what expires by month) **[W2]**; **Supplier Performance** (recalls / rejected
lots / expiry losses / quality failures per supplier) **[W2]**; **Lot Audit Score** (completeness:
batch/supplier/mfg/expiry/barcode/timeline) **[W2]**. Oldest-Stock (FIFO age) unchanged.
12.2 **Dashboards [W2]:** Perishable dashboard (expired / near-expiry tiers / quarantine / recall /
destroyed / value-at-risk / top-expiring); **Stock Health Score** (% healthy / near-expiry /
expired / recalled / quarantined).
12.3 **Expiry Risk Engine [W2 — flagship].** Beyond static day-thresholds, project **remaining
shelf life vs forecast consumption** to classify each lot/product **HIGH / MED / LOW** risk of
expiring before it can be used (e.g. *Feed: 600 kg, 10 kg/day, expires in 20 d, needs 60 d → HIGH*).
**Integrates the existing `wms_ai_forecast` module** for the consumption rate. This is the most
actionable expiry signal in the system.
12.4 **Alerts:** thresholds **[OWNER-7] 180/90/60/30/15/7/expired**; inbox + optional email; weekly
(existing) + optional daily; quiet when empty; active-recall alert immediate.

## 13. Migration strategy
Three paths: fresh DB / per-product-at-zero-stock / legacy-lot bulk (backup-first; restore =
rollback). Auto-enable only on new products. Detail: [`03`](03-database-and-migration.md).

## 14. Out of scope (do not build unless users ask)
Automated temperature / cold-chain **IoT sensors**; AI expiry *prediction beyond* the forecast-fed
Risk Engine (§12.3); demand forecasting rebuild; QR inventory map; voice issue; offline sync;
per-animal traceability; standalone whole-sequence transaction simulator (inline preview §7.4
suffices).

## 15. Change control
Once approved, **frozen**: implement against it; no new features/scope until v20 is complete &
re-certified. Defects fixed; new ideas logged for a future wave. Wave 2 begins only after 2–4 weeks
of real Wave-1 use.

## 16. Extensibility — versioned extension points
Stable, documented hooks at each flow's commit point — **receipt / issue / recall / quarantine /
disposal** — each receiving the lot(s) + context, overridable via `_inherit`, so future modules
(analytics, cold-chain, supplier portals, the Risk Engine) attach **without editing
`_wms_sorted_for_removal` or the wizards**. Receipt/issue/recall/quarantine hooks ship with their
Wave-1 flows (bodies may be no-ops); the disposal hook is stubbed in W1, used by W2. **The hook set
is versioned — `v20 Hook API 1.0`** — so a later `2.0` can add capabilities without breaking 1.0
extensions. Signatures are part of the frozen contract.

---
### Owner sign-off — ✅ COMPLETE (2026-06-24, all at recommended defaults)
- [x] OWNER-1 downstream recall tracing = **department level** (not per-animal)
- [x] OWNER-2 returned cold-chain perishables → **quarantine** (shelf-stable → original lot)
- [x] OWNER-3 FEFO shortfall → **allow partial issue** + record shortage
- [x] OWNER-4 manual cold-chain hold; **inbound-QC default OFF**
- [x] OWNER-5 **managers-only** for override / correct-expiry / quarantine / recall / dispose / create-dup-lot
- [x] OWNER-6 **auto-quarantine-expired default OFF** (expired stays put, blocked + flagged)
- [x] OWNER-7 alert thresholds **180/90/60/30/15/7/expired**
- [x] OWNER-8 duplicate uniqueness key = **(company, product, batch, expiry)** — supplier **NOT** included
- [x] OWNER-9 **per-kind shelf-life table (§2.8 as written)**; near-expiry guard = **warn + manager approval** (per-kind reject optional)
- [x] **SPEC APPROVED & FROZEN (2026-06-24).** Implementation gated on: (a) v19 certified & frozen, (b) v20 branch cut — then run [`08`](08-implementation-prompt.md).

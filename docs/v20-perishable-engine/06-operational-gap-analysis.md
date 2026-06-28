# v20 Operational Gap Analysis

> Purpose: stress-test the v20 design (docs 01–05) against real warehouse scenarios **before**
> the functional spec is frozen. Each scenario records: what the current design does → whether
> there's a gap (✅ covered / 🟡 partial / 🔴 new) → the resolution. Items marked **[OWNER]** are
> policy decisions for the trust to confirm; the rest are engineering decisions.

## A. Scenarios from the owner's list

### A1. Same medicine, 10 different batches  → ✅ covered
One product, 10 lots, each its own expiry. FEFO orders all 10; issuing auto-splits across the
earliest-expiring ones. **Watch-item (not a gap):** the issue preview and receipt screens must
stay readable at 10+ lots — paginate/scroll the plan, show only the lots being pulled, not all 10.
Lot name = the supplier's batch number (human-meaningful).

### A2. One batch recalled  → 🟡 partial (extend)
Design freezes the lot (excluded from picker), locates current stock, shows history. **Gaps:**
(a) **reserved / in-flight** stock of a recalled lot must be **un-reserved** and pulled from any
open issue; (b) stock **already issued downstream** (in the cow hospital / consumed) must be
surfaced — the recall report must list affected issue transactions + recipient department/keeper
+ date, even though it can't be physically retrieved. Resolution: recall freeze also cancels open
reservations for the lot; the recall report joins `stock.move.line` history (lot → issues →
department/keeper). "Affected animals" = the department/usage-note on those issues (the system
tracks department, not individual animals — that's the honest limit). **[OWNER]** confirm that
department-level downstream tracing is sufficient (vs per-animal, which the WMS does not model).

### A3. One batch quarantined  → 🟡 partial (extend)
Design covers **inbound** QC (receive → Quarantine → approve). **Gap:** quarantining a lot that's
**already in storage** (e.g., a defect found after putaway, a vet flags a bad batch). Resolution:
a "Move lot to Quarantine" manager action that relocates all of a lot's quants to the Quarantine
location (excluded from picker) and sets `wms_lot_state='quarantine'`; approve → back to storage,
reject → recalled/destroyed.

### A4. Supplier sends the wrong expiry  → 🔴 new
Nothing in 01–05 lets you correct a lot's expiry after receipt. Resolution: a **manager-only,
audited "Correct lot expiry"** action on `stock.lot` (logs old→new in the chatter, re-stamps
`wms_effective_expiry`, re-evaluates FEFO + alerts). **[OWNER]** confirm managers (not keepers)
hold this.

### A5. Half a feed sack consumed  → ✅ covered
Feed UoM is kg. Issue 5 kg of a 50 kg lot → 45 kg remains on the **same lot**, no new lot.
**Note:** measured (non-"Units") UoM already triggers the existing photo-required gate at issue —
that stays, giving an evidence trail for partial measured issues.

### A6. Vaccines lose cold-chain  → 🔴 new (scoped)
No temperature/cold-chain concept exists today. A cold-chain breach condemns a lot **regardless of
expiry**. Resolution: model it as a **quality hold** — the same "Move lot to Quarantine" action
(A3) with reason `cold_chain`, then approve-back or condemn (destroy). **Out of scope (explicit):**
automated temperature monitoring / IoT sensors — that's speculative until users ask. The engine
provides the *hold + condemn + audit* mechanism; the *detection* stays manual/operator-driven.
**[OWNER]** confirm manual cold-chain hold is acceptable for the pilot.

### A7. Barcode damaged  → ✅ covered (+ small add)
The scan wizards already allow **manual selection** (search by product/SKU/lot/batch) when a scan
fails — not scan-only. Add: a **reprint-lot-label** action so a damaged lot label can be
re-stuck. No structural gap.

### A8. Keeper issues the wrong lot  → 🟡 partial (extend)
FEFO **auto-selects** the correct lot; the keeper can't freely pick, and a deliberate bypass
demands a warning + confirm (and, if it skips an earlier-expiry lot, a manager-audited override).
**Gap:** if a wrong issue is still committed (bypass + mistake), the **reversal** path must restore
the qty to the **correct original lot**, not a generic pool. Resolution: issue-reversal carries the
`lot_id` back to its source lot (the system already has reversed-issue handling; extend it to be
lot-aware).

### A9. FEFO cannot satisfy the requested quantity  → 🟡 partial (extend)
The planner already returns `(plan, missing)` and shows a STOCK-OUT message. **Gap:** with v20,
"available" shrinks because expired / quarantined / recalled stock is **excluded** — the keeper
must see *why*. Resolution: the shortfall message breaks it down — "Requested 50; planned 30 from
2 lots; 20 short — 15 excluded (expired), 5 (quarantined)." **[OWNER]** partial-fill policy: allow
the partial issue + record the shortage (recommended, matches today), **or** block until full?
Default = allow partial with explicit shortage.

### A10. Stock exists without a lot  → ✅ covered
`wms_effective_expiry` falls back to the template date, then `in_date` (i.e., behaves like today's
FIFO) for un-lotted stock. The legacy-lot migration assigns a legacy lot; a self-diagnostics probe
flags perishable on-hand that lacks a lot. During transition a product may briefly hold both
lotted and un-lotted stock — FEFO treats un-lotted as "no expiry" (sorts last), which is safe
(expiry-bearing lots go first).

## B. Additional scenarios the design must answer

### B1. Two lots, identical expiry  → ✅ covered
Tie-break: expiry → `in_date` → `id` (deterministic, oldest arrival first).

### B2. Expired stock physically present  → 🟡 detail (Wave 2)
The `destroyed` lifecycle state exists but its **mechanics** aren't specified. Resolution: a
manager **"Dispose/Destroy lot"** action → moves to a disposal location / scraps, sets
`destroyed`, writes off value, logs reason + qty + approver. Feeds the wastage analytics.
**[OWNER]** confirm disposal authority = managers; optional `auto-quarantine-expired` setting
(default OFF — expired stock stays put but is blocked at issue + flagged).

### B3. Returned perishable stock may be compromised  → 🔴 new [OWNER]
Returning issued stock to its original lot is fine for shelf-stable items, but a returned
**vaccine/cold-chain** item may no longer be safe. **[OWNER] policy:** for cold-chain-sensitive
kinds, returns go to **Quarantine** (QC before restock) instead of straight back to the lot; for
shelf-stable perishables, restock to the original lot. Default recommendation: quarantine-on-return
for `vaccine` + any kind flagged cold-chain; restock-to-lot otherwise.

### B4. Reservation interplay with recall/quarantine  → 🔴 new detail
Freezing a lot (recall/quarantine) must **cancel its open reservations** so the stock can't be
issued from a pending picking. Resolution: the freeze action unreserves the lot's quants first.

### B5. Concurrent issues racing for the earliest-expiry lot  → ✅ covered
The Scan Issue path already locks per-product (`FOR UPDATE`); extend the lock to be lot-aware so
two keepers can't both claim the last unit of LOT-C.

### B6. Inventory adjustment / cycle count on a lot-tracked product  → 🟡 note
Counts/adjustments must be **per lot** (you count LOT-A and LOT-B separately). The existing cycle-
count flow must surface lot + expiry. Resolution: cycle-count screens become lot-aware for
perishables (Wave 2; non-blocking for Wave 1).

### B7. Transfer between slots  → ✅ covered
A slot-to-slot move keeps the lot (and thus its expiry) — Odoo native; no special handling.

### B8. Multi-warehouse lot scoping  → ✅ covered
The planner already scopes to the warehouse's `lot_stock_id` subtree (with a company-wide
fallback). Lots are company-scoped. No change.

### B9. Analytics need history from day 1  → 🟡 note
Dashboards/analytics are Wave 2, but the **events they need** (issued, expired, destroyed, with
lot + qty + date) must be captured from **Wave 1** so Wave-2 analytics aren't blind to the pilot
period. Resolution: ensure lot + expiry land on every move-line from Wave 1 (they do, via the
receipt/issue lot plumbing) — no extra event log needed; the stock.move.line history is the source.

### B10. Duplicate lot from a typo'd batch  → 🔴 new (owner-flagged)
Two receipts of the same product with the **same batch number** (e.g. ABC123 / 2027-04-01 entered
twice) would create two phantom lots — mis-splitting FEFO and corrupting traceability. Resolution:
**duplicate-lot detection** at receipt — if (product, batch) already exists, prompt: *add to the
existing lot* / *cancel* / *create new* (manager-only). Spec §3.6. *(Wave 1.)*

### B11. Fast handling at scale (receive/issue/recall/audit)  → 🔴 new (owner-flagged)
Scanning a product then hunting for the right lot is slow at 10+ lots. Resolution: a **per-lot
barcode** (printed on the lot label) — one scan resolves to the lot and shows product, batch,
expiry, location, remaining. Spec §2.5. *(Wave 1.)* Plus a **lot timeline** (full per-lot history)
for inspections — §2.6. *(Wave 1 basic / Wave 2 polished.)*

## C. Summary — what the gap analysis changes

**New requirements surfaced (fold into the functional spec):**
1. Post-receipt **lot-expiry correction** (manager, audited) — A4.
2. **Quarantine an existing stored lot** (manager hold), not just inbound — A3.
3. **Quality / cold-chain hold + condemn** (manual; IoT out of scope) — A6.
4. Recall must handle **reserved/in-flight** (unreserve) and **downstream-issued** (trace
   transactions) stock — A2, B4.
5. **Lot-aware issue reversal** (restore to the correct lot) — A8.
6. **Shortfall breakdown** showing excluded expired/quarantined/recalled stock — A9.
7. **Disposal/destroy** mechanics + value write-off + audit — B2.
8. Lot-aware **lock**, **cycle count**, and **reprint-lot-label** — B5, B6, A7.
9. **Duplicate-lot detection** at receipt (add / cancel / create-new-manager-only) — B10.
10. **Per-lot barcode** + **lot timeline** (full per-lot history) — B11.

**Owner policy decisions to confirm before the spec is frozen:**
- [OWNER-1] Downstream recall tracing at **department** level (not per-animal) is sufficient — A2.
- [OWNER-2] Returned cold-chain perishables → **quarantine** (vs restock-to-lot) — B3.
- [OWNER-3] FEFO shortfall → **allow partial issue** + record shortage (vs block) — A9.
- [OWNER-4] Manual cold-chain hold acceptable for the pilot (no sensors) — A6.
- [OWNER-5] Authority: only **managers** may override-expired, correct-expiry, quarantine, recall,
  dispose — A4, A6, B2.
- [OWNER-6] `auto-quarantine-expired` default **OFF** (expired stays put, blocked + flagged) — B2.
- [OWNER-7] Confirm alert thresholds **180/90/60/30/15/7/expired**.

**Verdict:** the core design (lot/FEFO/issue-safety/reports) is sound and complete enough to build
Wave 1. The gap analysis exposed **10 new requirements**, all of which **reuse existing
mechanisms** (quarantine location, recall model, approval gate, reversal, label engine + barcode
`resolve()`, move-line history, chatter audit) rather than new subsystems. **Wave 1** (per the
owner's tightened split) now carries the safety-critical ones: lot-aware reversal, shortfall
breakdown, unreserve-on-freeze, recall-freeze + quarantine **exclusion**, **duplicate-lot
detection**, **per-lot barcode**, and a **basic lot timeline**. The analytical/visual extensions
(dashboards, value-at-risk/wastage/supplier-quality analytics, disposal mechanics, cold-chain
workflow, cycle-count, polished timeline) move to **Wave 2** after the pilot. No finding
invalidates the architecture in 01.

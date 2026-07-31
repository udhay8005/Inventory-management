# v20 Architecture — Universal Perishable Engine

## 1. Design principle

```
ONE Product  →  MANY Lots  →  MANY Movements  →  MANY Locations
```

- A different expiry is a different **lot of the same product** — never a new product, never a
  merged quantity.
- Lots are **never merged** (even same supplier / same expiry / same product).
- Partial issue, partial return, and damage keep the **same lot** (a smaller remaining qty on
  the same lot — no new lot).
- **FEFO** (earliest expiry first) for perishables; **FIFO** (oldest arrival) for everything
  else. Both already live in one ordering method — see §4.
- Every receipt / issue / damage / return / move is attributable to a lot (traceability).

## 2. Module strategy — additive, frozen v19 untouched

v20 ships as **one new addon, `wms_perishable`**, depending on `wms_location, wms_fifo,
wms_barcode, wms_repair_damage, wms_reports, stock, product_expiry, mail`. It uses Odoo
`_inherit` to extend existing behaviour and owns all genuinely new models, views, reports, and
the dashboard. The certified v19 addons are **not modified** — this is what makes "freeze v19
forever" literally true.

What that means concretely:

| Change | Mechanism (no v19 edits) |
|--------|--------------------------|
| FEFO sort keys on lot expiry | `_inherit = "stock.quant"` → override `_wms_sorted_for_removal` (call `super()`, re-sort) and add a stored `wms_effective_expiry` field |
| Quarantine / Recall excluded from picker | `_inherit = "stock.location"` → add `wms_is_quarantine` / `wms_is_recall`; `_inherit = "stock.location"` model method or a thin override of `find_oldest_quants_for_product` to add the two domain leaves |
| Batch/expiry/supplier capture at receipt | `_inherit = "wms.scan.receipt.line"` (transient) → add fields; view inheritance (xpath) to render columns; `_inherit = "wms.scan.receipt"` → extend `action_validate` to create the lot |
| Expired-issue block + FEFO-bypass warning + preview | `_inherit = "wms.scan.issue"` → extend `action_plan` / `action_validate`; `_inherit = "wms.issue.approval"` → add `reason_expired` |
| Perishable products auto-enable lot+expiry | `_inherit = "product.template"` → extend `create()`; extend the create/onboard wizards |
| Per-lot reports, dashboard, recall, lifecycle, settings | **new models** owned by `wms_perishable` |

> Trade-off acknowledged: a few overrides (the sort-key lambda, the receipt `action_validate`
> extension) are tighter couplings to v19 internals. They are small and well-localised; the
> alternative (editing the frozen addons) is worse. If a v19 method ever needs a hook it does
> not expose, that single hook is the *only* permitted surgical edit to a frozen addon, made as
> its own commit with a clear note.

## 3. Data model (new, owned by `wms_perishable`)

### 3.1 Lot extension (`stock.lot` via `_inherit`)
- `expiration_date` — from Odoo `product_expiry` (do **not** hand-roll). Manufacture/removal/
  alert dates come with it.
- `wms_lot_state` — Selection: `available` (default) / `quarantine` / `recalled` / `destroyed`.
  **"reserved" is NOT modelled** (Odoo quants already track `reserved_quantity`); **"expired" is
  NOT a stored state** (computed from `expiration_date < today`).
- `wms_supplier_id`, `wms_supplier_batch`, `wms_supplier_invoice`, `wms_manufacture_date` —
  captured at receipt for traceability/recall.

### 3.2 `stock.quant` extension (via `_inherit`)
- `wms_effective_expiry` (Date, **stored, indexed**, computed) =
  `lot_id.expiration_date or product_tmpl.wms_expiry_date`. This is the single value the FEFO
  sort reads (keeps the sort fast and the lambda simple). `@api.depends("lot_id.expiration_date",
  "product_id.product_tmpl_id.wms_expiry_date")`.

### 3.3 `stock.location` extension (via `_inherit`)
- `wms_is_quarantine` (Boolean) — like `wms_is_damage`; excluded from the picker.
- `wms_is_recall` (Boolean) — physically-segregated recalled stock; excluded from the picker.

### 3.4 New model `wms.lot.recall`
Fields: `lot_id` (required), `product_id` (related, stored), `supplier_id`, `recall_date`,
`reason` (supplier/quality/regulatory), `description`, `state` (active/resolved/disposed),
`action_required`. Creating an **active** recall flags the lot (`wms_lot_state='recalled'`),
which excludes its quants from the picker, and notifies managers. Actions: freeze, resolve,
dispose. Drives the recall report (locate everywhere + full history + remaining stock).

### 3.5 New model `wms.perishable.settings` (or scoped System Parameters)
Configurable: alert thresholds **180 / 90 / 60 / 30 / 15 / 7 / expired**; daily-vs-weekly digest;
email-on/off; optional auto-quarantine-expired + a disposal location. Stored so the SQL views /
crons read them rather than hard-coding 30/90.

### 3.6 New report models (`_auto=False` SQL views, the `wms.returns.due.report` pattern)
`wms.expiry.lot.ledger` (per-lot on-hand by location, FEFO-sorted) · `wms.lot.traceability`
(supplier→PO→lot→receipt→location→keeper) · re-keyed `wms.expiry.alert` (per-lot, recall-aware,
threshold-configurable). Plus the Perishable Dashboard controller route.

## 4. The FEFO engine (the heart — one override)

`stock.quant._wms_sorted_for_removal` is the **single authoritative removal order**, shared by
the Scan Issue planner and Odoo's `_gather`. Today it keys FEFO on the *template* expiry, which
collapses to FIFO because one issue = one template = one date. v20 keys it on
`wms_effective_expiry` (per-lot), so issuing auto-picks the earliest-expiring lot and
auto-splits across lots:

```
order = (wms_effective_expiry ASC, in_date ASC, id ASC)   # for perishable kinds / has-expiry
order = (in_date ASC, id ASC)                              # everything else — unchanged
```

Because both the planner and `_gather` delegate here, one override lights up FEFO everywhere.
The exclusion domain (`find_oldest_quants_for_product`) gains two leaves so quarantine/recalled
stock is never planned.

## 5. End-to-end flows

```
RECEIPT   scan product → enter Batch + Expiry (+ supplier/invoice/mfg) → create/find lot
          (never merge) → place quant (or → Quarantine if QC on) → print label
QC/QUAR.  Quarantine location → quality check → approve → move to storage (now pickable)
                                              → reject → Recalled/Destroyed
ISSUE     scan product + qty → planner FEFO-orders lots → PREVIEW (lots pulled + resulting
          balances) → expired? BLOCK (manager approval + audit reason) → bypass-FEFO? WARN +
          confirm → commit
DAMAGE    damage N of a lot → remaining stays on the same lot, history preserved
RETURN    return → original lot when known
RECALL    flag lot → freeze (excluded from picker) → locate everywhere + full history → report
REPORTS   per-lot expiry alert (configurable tiers) + lot ledger + traceability + recall +
          dashboard (expired / near-expiry / quarantine / recall / destroyed / value-at-risk)
ALERTS    daily/weekly digest at configured thresholds → managers (inbox + optional email)
```

## 6. Open-strip decision (locked)

Track **tablets/units only** (Option 1). One strip = N tablets; receive 100, issue 7, balance
93. Pack-size stays a label in the SKU; whole-strip scanning uses the existing barcode alias
`units_per_scan`. **No** closed/open/loose-strip split (pharmacy-grade complexity a gaushala
doesn't need).

## 7. Inventory preview (folds the owner's "Transaction Simulator" into Wave 1)

The Scan Issue wizard already shows the planned deductions before commit. Wave 1 adds, to that
existing preview: the FEFO order and the **resulting lot balances** (LOT-A → 80, LOT-B → 150)
before Confirm. A standalone whole-sequence simulator is deferred to Wave 2 *only if* real use
shows commit-order mistakes.

## 8. Extensibility — extension points (foundational subsystem)

v20 is a foundation other modules will build on, so it ships **documented, stable hooks** at the
commit point of each flow — **receipt, issue, recall, quarantine, disposal** — each receiving the
affected lot(s) + context and overridable via `_inherit`. This is what lets future modules
(analytics, cold-chain, supplier portals) attach **without ever editing `_wms_sorted_for_removal`
or the wizards**. The receipt/issue/recall/quarantine hooks are added *with* their Wave-1 flows
(bodies may be no-ops); the disposal hook is stubbed in Wave 1 and used by the Wave-2 disposal
workflow. Hook signatures are part of the frozen contract (spec §16) and don't change without a
version bump.

# 20 — End-to-end flow

How a product moves through the WMS, from the moment the Admin first
records it to the moment it leaves the warehouse (or gets repaired,
returned, or replaced). Read this once and the logic of every wizard
should click into place.

```
            ┌──────────────────────────────────────────────────────┐
            │                       ADMIN                          │
            │  Create product → assign barcode → classify (Kind)   │
            │                                                      │
            │     • Inventory → Products → New                     │
            │     • Reference (SKU) = RM-/PK-/FL-/FG-/CONS-/…      │
            │     • Barcode = same SKU by default                  │
            │     • WMS Classification tab → Kind + Returnable     │
            └─────────────────┬────────────────────────────────────┘
                              │
                              │  Product exists in catalogue with a
                              │  unique barcode. Nothing on a shelf yet.
                              ▼
            ┌──────────────────────────────────────────────────────┐
            │                  STORE KEEPER                        │
            │  Scan Receipt  (Operations → Scan Receipt)           │
            │                                                      │
            │   1. HID scanner reads the barcode  → product line   │
            │      is added to the wizard with quantity 1          │
            │      (or N if it's a carton-barcode alias)           │
            │   2. Optionally scan a slot barcode to pin the       │
            │      destination — otherwise the wizard auto-picks   │
            │      a slot already holding this product, an empty   │
            │      slot, or a floor zone, in that order            │
            │   3. Tick "Quality check passed" + Validate          │
            │                                                      │
            │   Validate creates a stock.picking → stock.move →    │
            │   stock.move.line → stock.quant. The quant is the    │
            │   "where is it" truth from this point on.            │
            └─────────────────┬────────────────────────────────────┘
                              │
                              │  Product now lives in a specific slot
                              │  with timestamp = receipt time, which
                              │  becomes the FIFO age.
                              ▼
            ┌──────────────────────────────────────────────────────┐
            │      "Where is it?" — visible from many places       │
            │                                                      │
            │   • Smart button on the product form:                │
            │       "5 slot(s) · 42 on hand"                       │
            │     → opens a per-slot breakdown                     │
            │   • Reports → Where is product X?                    │
            │   • Reports → Slot occupancy heat-map                │
            │   • Configuration → Racks → Open visual grid         │
            │     → coloured CSS grid of the rack contents         │
            │   • Reports → Warehouse map                          │
            │     → top-level zone × rack summary                  │
            └─────────────────┬────────────────────────────────────┘
                              │
                              │  Daily operations: someone needs the
                              │  product. They walk to the store desk.
                              ▼
            ┌──────────────────────────────────────────────────────┐
            │                  STORE KEEPER                        │
            │  Scan Issue  (Operations → Scan Issue (FIFO))        │
            │                                                      │
            │   1. Scan product barcode + quantity                 │
            │   2. The wizard plans FIFO: oldest slots first       │
            │      across the whole warehouse                      │
            │   3. Audit trail (required at Validate):             │
            │      • Taken by   — name of the person receiving     │
            │      • Ordered by — name of who authorised it        │
            │      • Store Keeper on duty — picked from the        │
            │        roster the Admin maintains                    │
            │   4. Photo capture is forced for measured items      │
            │      (litres / kg / m³) — proof of dispensed qty     │
            │   5. Validate → stock.picking flows the qty to       │
            │      Customers / Production / Internal location      │
            │                                                      │
            │   STOCK OUT flow: if there isn't enough on hand,     │
            │   the wizard refuses to validate and shows a clear   │
            │   "⚠ STOCK OUT — only Scan Return / Scan Receipt     │
            │   can bring this back." message. No silent partial   │
            │   issues.                                            │
            └────────┬─────────────────────────────────┬───────────┘
                     │                                 │
        Returnable item                        Non-returnable item
        (Tool, Spare, RM, PK, FG, WIP)        (Fluid, Consumable)
                     │                                 │
                     ▼                                 ▼
    ┌─────────────────────────────┐    ┌─────────────────────────────┐
    │  Scan Return when it comes  │    │  Item is gone — that's it.  │
    │  back from the worker /     │    │  The audit trail still says │
    │  production. Same wizard,   │    │  who took it and when. The  │
    │  "Return entry mode" on.    │    │  buying-recommendation      │
    │  Non-returnable products    │    │  engine factors this into   │
    │  are refused at Validate.   │    │  the daily-avg consumption. │
    └─────────────────────────────┘    └─────────────────────────────┘
```

## Damage flow — the smart branching

Reality: things break. When the Store Keeper opens
`WMS → Operations → Damages → New` and picks a product + quantity, the
form **automatically** classifies what should happen next.

| Situation | What the form says | Action |
|---|---|---|
| Damaged item is the only one we own AND it's not returnable (fluid / consumable) | **⚠ URGENT BUY** banner | Buy a fresh batch — the item can't be repaired and there's no spare |
| Damaged item is the only one we own AND it IS returnable (tool / spare) | "Only one — repair needed" warning | Open a Repair Order; until it returns, the item is unavailable |
| Damaged item is returnable AND we have other units | "Open a Repair Order" info | Repair at leisure; work isn't blocked |
| Damaged item is non-returnable but plenty more on hand | "Just a note" muted note | Logged for audit. Buying-recommendation engine factors this into the next daily-avg pass |

The decision is based on **`remaining_on_hand`** (computed from
`stock.quant` excluding the damage qty) and the product's
**WMS Kind / Returnable** flag. Both are computed live — no manual
refresh.

## Buying recommendations — the brain over the audit trail

The `wms.buying.recommendation` engine reads the last 30 days of
stock movements and per-product audit data, then produces one row per
product with a buy quantity and a plain-English reason.

For **returnable** items it counts *concurrent users*: if three
different people had the wrench out at the same time last week and
the warehouse only owns one, the engine suggests buying two more so
nobody has to wait. Repeated borrowing by the same person counts as
one and doesn't trigger a recommendation.

For **non-returnable** items it computes daily / weekly / monthly
averages from the last 30 days of issues, projects the next 30 days
of demand at that rate, adds a 7-day safety buffer, and recommends
topping up to that target if current stock can't cover it.

Urgency bands (used for the list-view colour decoration):
- **CRITICAL** — on hand is zero AND there have been issues
- **HIGH** — recommended buy > 0 AND ≤ 7 days of stock left
- **MEDIUM** — recommended buy > 0 AND ≤ 30 days of stock left
- **LOW** — recommended buy > 0 otherwise
- **OK** — no action needed

Refreshed nightly at 02:00 by a scheduled task. The list view has a
**Refresh recommendations** button for on-demand refresh.

## Roles in one paragraph

**Admin (WMS / Manager)** — adds products, sets barcodes, assigns the
WMS Kind, classifies returnability, creates racks / compartments /
slots, maintains the Store Keeper roster, prints sticker labels,
configures the thermal printer layout, reviews buying recommendations,
opens repair orders.

**Store Keeper (WMS / Store Keeper)** — scans receipts in, scans issues out,
notes who took what, validates returns, records damage events. Cannot
edit products, slots, the storekeeper roster, or label settings.
Reads every report (occupancy, oldest stock, where-is-X, cycle count
due, buying recommendations) for the weekly audit pass.

## The promise the system makes

1. Every storable item has **exactly one barcode** that's unique
   across the trust.
2. Every move (in or out) is recorded as a `stock.picking` with a
   human name (taken-by / ordered-by) and the on-duty Store Keeper.
3. The location of every unit is **always** queryable in real time —
   from the product form, from any report, from the visual rack grid.
4. The system never silently fails: if there isn't enough stock, the
   issue refuses to validate; if a return doesn't match the
   returnability flag, the receipt refuses; if a damage leaves zero
   spares, the form shouts "URGENT BUY".
5. Nothing is ever auto-deleted. Archived users, retired Store
   Keepers, replaced products — they stay in the history forever.

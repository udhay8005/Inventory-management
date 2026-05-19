# 03 — Workflows

All stock-moving workflows in the WMS share a single invariant: **every
resulting `stock.picking` carries the audit triplet** (`wms_taken_by` /
`wms_ordered_by` / `wms_storekeeper_id`) + a chatter message. The wizards
fill the audit fields at form time; the trust's reports key off the picking
so damage / repair / receipt all look the same.

## Inbound — Scan Receipt

1. **WMS → Operations → Scan Receipt** (Store Keeper or Manager).
2. The wizard opens with:
   - Scanner field (cursor auto-focused, USB/Bluetooth HID just types into it)
   - Lines table (auto-filled as you scan; carton barcodes auto-fill unit count)
   - QC checkbox (mandatory) + free-text notes
   - **Audit panel**: Store Keeper on duty (M2O, required) + Delivered by (Char)
3. Scan product / carton / slot barcodes; the wizard resolves via `wms.barcode.alias`
   - **Product / alias / lot** scan → adds a line
   - **Location** scan → assigns to the most recent line without a destination
4. *Process scan* button (alternative to auto-process on barcode_events_mixin)
5. *Validate & Print* — refuses to proceed if:
   - QC checkbox unticked → `UserError`: "Mark 'Quality check passed' first"
   - Storekeeper field empty → required-field error
   - Return mode + product not returnable → `UserError` listing the offending lines
6. Creates `stock.picking` of warehouse-level `in_type_id` (auto-unarchives if needed),
   sets `wms_taken_by = delivered_by`, `wms_storekeeper_id = storekeeper_id`,
   moves stock to auto-assigned or operator-chosen slot/floor zone, validates.
7. Chatter audit posted: "*Receipt received. Delivered by X; Store Keeper on duty: Y;
   logged in as: Z.*"

### Slot auto-assign priority

`scan_receipt._auto_assign_slot`:

1. A slot or floor zone already holding this product (cluster)
2. Any empty rack slot
3. Any empty floor zone
4. Any rack slot (warning — will mix products)
5. Any floor zone

## Inbound — Scan Return

Same wizard, opened via **Scan Return** menu (`default_is_return=True` in
context). Adds one extra check at Validate: any line whose product has
`wms_is_returnable = False` is refused with a list of which products + their
WMS Kind. Fluids and consumables fail this; tools, spares, raw materials pass.

## Outbound — Scan Issue (FIFO)

1. **WMS → Operations → Scan Issue (FIFO)**.
2. Wizard opens with:
   - Scan field + Requested Qty (operator can adjust between scans for bulk)
   - Destination (defaults to Customers)
   - Audit panel: Taken by + Ordered by + Store Keeper on duty
   - Item photo upload (mandatory if the planned product's UoM ≠ Units)
3. Scan triggers `find_oldest_quants_for_product` across all slots/floor zones
   under the warehouse's stock location → planned deductions shown BEFORE validate
4. Plan rows are editable; operator can reduce qty if a slot is physically empty
5. *Validate* — refuses if:
   - No lines planned (nothing scanned yet)
   - `short_qty > 0` (stock-out — better to flag the Admin than partial-issue)
   - Photo required and missing
6. Creates `stock.picking` of `out_type_id` (or `int_type_id` if destination is
   internal), one `stock.move` per (product, source-slot) pair, validates.
7. Chatter audit + optional photo attached as `ir.attachment` on the picking.

## Damage

1. **WMS → Operations → Damages → New** (any role).
2. Form has two side-by-side groups: "What & where" + "Who reported it".
3. As soon as product is picked, the **recommendation engine** computes
   `recommended_action` and shows a banner:

   | Branch | Trigger | Banner |
   |---|---|---|
   | `urgent_buy` | non-returnable + 0 spare anywhere | ⚠ URGENT BUY (red) |
   | `repair_returnable_only` | returnable + 0 spare | Only one — repair needed (yellow) |
   | `repair_returnable` | returnable + ≥1 spare | Open a Repair Order (blue) |
   | `repair_with_spare` | non-returnable tool/spare + ≥1 spare | Assess: repair or scrap? (blue) |
   | `note_only` | non-returnable + spare on hand | Just a note (grey) |

4. Slot dropdown shows both slots and floor zones (`wms_location_type in ('slot','floor')`).
5. *Confirm* — refuses with `UserError` if:
   - Quantity exceeds `(total - reserved)` at the slot (so an in-flight Scan Issue can't be over-allocated against)
   - Any audit field is blank
6. Creates internal `stock.picking` source → Damage location, copies audit
   triplet onto the picking, posts "*Damage confirmed. Reported by X; …*" chatter.
7. If `recommended_action = 'urgent_buy'`, fans out a Discuss notification to
   every WMS Manager via `partner_id.message_post()`.

## Repair

A wms.repair.order is created either:

- **From a damage event**: click *Create Repair Order* button on the damage form
  (visible only when `state=confirmed` AND no existing `repair_order_id` AND
  recommended_action is one of `repair_returnable*` / `repair_with_spare`).
  Pre-fills product / quantity / original_slot / return_slot / audit triplet
  from the damage. Damage event back-references via `repair_order_id`.
- **Standalone**: Manager opens **WMS → Operations → Repair Orders → New**.

State machine:

```
draft ──Start Repair─→ in_repair ──Mark Done─→ done
  │                       │
  │                       └──Scrap─→ scrapped
  └──Cancel─→ cancelled
```

Each transition:

- **action_start_repair** (draft → in_repair): creates internal picking Damage → Repair-Out, copies audit triplet, validates.
- **action_finish_repair** (in_repair → done): creates internal picking Repair-Out → return slot (defaults to original), copies audit triplet, validates.
- **action_scrap** (in_repair → scrapped): Odoo native `stock.scrap` from Repair-Out.
- **action_cancel** (draft only → cancelled): guards refuse cancel on in_repair (must Finish or Scrap first to avoid orphan stock at Repair-Out) and on done/scrapped (terminal).

Every transition calls `_post_state_audit()` which posts a chatter message
with the audit triplet + the on-duty Odoo login.

`_check_audit_complete()` runs at every transition (except cancel): all three
audit fields must be filled or the action raises `UserError` listing what's
missing.

### Visibility

- **Store Keepers** see Repair Orders only through the back-link on their
  damage event (the *Linked repair order* field). They can read the order
  but not edit; the state-transition buttons are hidden via `groups=` so
  they don't dangle dead UI.
- **Repair Tech / Manager** see the *Repair Orders* menu under Operations.

## Cycle count

Pure Odoo `stock.quant` *Inventory Adjustments* with WMS-specific filters
per slot. No custom workflow; the WMS adds a *Cycle Count Due* report that
flags slots with `last_count_date older than N days`.

## State transitions summary

```
stock.picking      : draft → confirmed → assigned → done
wms.damage         : draft → confirmed | cancelled
wms.repair.order   : draft → in_repair → done | scrapped
                          └─→ cancelled
```

All transitions write a `mail.message` (Odoo chatter) for audit, and
WMS-specific transitions add an explicit `_post_state_audit()` message
with the human-readable triplet.

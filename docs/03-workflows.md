# 03 — Workflows

## Inbound (Purchase Receipt)

1. Purchase Order → Receipt (`stock.picking`, type incoming).
2. At dock: open *Scan Receipt* wizard (`wms_barcode`).
3. Scan product barcode → enter quantity → choose slot (or **Auto-Assign**).
   - Auto-Assign rule: first slot with `wms_capacity_units >= qty AND empty`,
     else first slot with same product, else first slot under same rack.
4. Wizard validates picking → `stock.move.line.location_dest_id = <slot>`.
5. `stock.quant` row created (or incremented) with `in_date = now()`.
6. (Optional) **Print labels** — product label + slot label.

## Outbound (Sales / Consumption)

1. Internal request or sale order → Delivery picking.
2. *Scan Issue* wizard: scan product barcode, enter qty.
3. FIFO removal strategy on the parent stock location returns the oldest
   `stock.quant`s across all slots; wizard pre-fills move lines from those slots.
4. Picker confirms (or overrides if a slot is physically empty) → validate.

## Internal transfer (slot ↔ slot)

- One-screen wizard: scan product, choose source slot (auto = oldest), choose
  destination slot, enter qty → generates an internal `stock.picking`.

## Damage

1. `wms.damage` form: product, qty, source slot, reason, optional photo.
2. Confirm → creates `stock.picking` (internal) source slot → Damage Location.
3. Damage Location is a normal internal location with `wms_is_damage=True` so
   valuation stays correct and reports can isolate it.

## Repair

1. `wms.repair.order` from a damaged quant (or directly from a slot).
2. State: *draft → in_repair → done / scrapped*.
3. `in_repair`: move from Damage → Repair-Out location (still internal so we
   own the inventory, just flagged).
4. `done`: move from Repair-Out back to **original slot** (default) or operator-
   chosen slot. Original slot is remembered on `wms.repair.order.original_slot_id`.
5. `scrapped`: Odoo `stock.scrap` from Repair-Out.

## Returns

- *Customer return*: existing Odoo flow; wizard nudges operator to pick a slot
  (oldest preferred receiving slot for that product, else any same-product slot,
  else empty slot).
- *Return from repair*: see Repair → `done`.

## Adjustments / Cycle counts

Pure Odoo `stock.quant` "Inventory Adjustments" — already audited and signed.
No custom path needed; we just add convenient filters per slot.

## Relocation

Same as Internal Transfer but defaulted to "same product, different slot."

## State transitions summary

```
draft → confirmed → done           (pickings)
draft → in_repair → done | scrapped (wms.repair.order)
draft → confirmed                   (wms.damage)
```

All transitions write `mail.message` entries (Odoo chatter) for audit.

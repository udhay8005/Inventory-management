# 02 — Data model

## Core: location hierarchy on top of `stock.location`

We **extend** `stock.location` instead of inventing a new tree. This keeps
Odoo's quant/move machinery working unchanged.

```
stock.warehouse
    └─ stock.location (view)        WH/Stock
        └─ rack    (view)           a shelf × column grid (default 6 × 3)
            └─ compartment (view)   a 2D rectangle on that grid
                └─ slot (internal)  holds stock; 1+ slots per compartment
```

The hierarchy is **3 levels deep**: Rack → Compartment → Slot. *Shelf* and
*Column* are **grid coordinates**, not separate `stock.location` rows. Each
rack carries `wms_shelf_count` × `wms_column_count`; each compartment occupies a
rectangle (`shelf_top..shelf_bottom` × `column_left..column_right`) on that
grid, so a compartment can be 1×1, tall (`SH01-03 C01`), wide (`SH01 C01-03`),
or a block (`SH01-03 C01-03`). A compartment holds `wms_slot_count` slots
(default 1 = the compartment itself is the storable unit).

Two non-rack location types complete the model:

- `zone` (view) — a building / floor / area that groups racks.
- `floor` (internal) — open / pallet / yard storage where quants land directly,
  with no compartment/slot underneath.

### Fields added to `stock.location` (in `wms_location`)

| Field | Type | Notes |
|---|---|---|
| `wms_location_type` | Selection | `warehouse_view` / `zone` / `rack` / `compartment` / `slot` / `floor` |
| `wms_rack_code` | Char | e.g. `R01`, `PHARM01` (on rack) |
| `wms_shelf_count` | Integer | Grid rows in this rack (default **6**) |
| `wms_column_count` | Integer | Grid columns in this rack (default **3**) |
| `wms_shelf_top` / `wms_shelf_bottom` | Integer | Top/bottom shelf rows a compartment occupies |
| `wms_column_left` / `wms_column_right` | Integer | Left/right columns a compartment occupies |
| `wms_slot_count` | Integer | Slots inside a compartment (default **1**) |
| `wms_slot_number` | Integer | Position of a slot inside its compartment |
| `wms_capacity_units` | Float | **Soft** capacity hint shown in UI; not hard-enforced |
| `wms_is_damage` | Boolean | Internal location holding damaged stock |
| `wms_is_repair` | Boolean | Internal location holding in-repair stock |

### Constraints (declarative `models.Constraint` + `@api.constrains`)

- `wms_shelf_count` ≥ 1 and `wms_column_count` ≥ 1 (a rack has at least 1×1).
- `wms_shelf_bottom` ≥ `wms_shelf_top`; `wms_column_right` ≥ `wms_column_left`
  (a compartment rectangle is well-formed).
- `wms_slot_count` ≥ 1.
- A compartment's parent must be a **rack**; a slot's parent must be a
  **compartment**; a compartment's rectangle must fit inside the rack's grid.

## Quantities

We don't add a quantity table. Use Odoo's `stock.quant`:

```python
stock.quant
  product_id      Many2one product.product
  location_id     Many2one stock.location   ← will be a slot
  lot_id          Many2one stock.lot
  package_id      Many2one stock.quant.package
  quantity        Float
  reserved_quantity Float
  in_date         Datetime           ← FIFO key
```

`in_date` is automatically set by Odoo on receipt. FIFO across slots = sort
`stock.quant` records by `in_date ASC` and consume in order. We do this with a
removal strategy (see `04-barcode-flow.md`).

## Custom transaction models (`wms_repair_damage`)

These are *wrappers* — they generate `stock.move`s, not bypass them.

```
wms.damage           ─ source slot ─→ Damage Location  (internal, wms_is_damage)
wms.repair.order     Damage Loc ─→ Repair-Out (vendor-style internal)
                                  └─→ back to source slot on completion
wms.return           customer ─→ Return holding ─→ original slot (or new)
```

Status fields, photos (`ir.attachment`), reason notes, and links to the
generated `stock.picking` go on these models.

## AI / forecast (`wms_ai_forecast`)

```
wms.forecast
  product_id           Many2one product.product
  horizon_days         Integer (default 30)
  predicted_qty        Float
  monthly_avg_qty      Float
  reorder_qty          Float           ← deterministic, computed from predicted
  reorder_date         Date            ← when stock will hit ROP
  velocity_class       Selection [fast, normal, slow, dead]
  is_consumable        Boolean (mirror of product type)
  last_trained         Datetime
  model_name           Char (e.g. "HoltWinters" / "SES" / "Manual")
  rmse                 Float
```

One row per product. Re-trained by cron daily. Old runs archived in
`wms.forecast.history` (small, ~one row per product per training).

## Reports / dashboards (`wms_reports`)

Most dashboards are SQL views (`models.Model` with `_auto=False`) built on top
of `stock.quant`, `stock.move`, `wms.forecast`. No data duplication.

## Indexes worth adding (already in models)

- `stock.location (wms_location_type)` — selective filter for "show all slots".
- `stock.quant (product_id, location_id, in_date)` — FIFO pickup query.
- `wms.forecast (product_id)` — UNIQUE.

## Why no separate slot_qty table

If you store quantity in two places (quant + your own slot table), they will
drift. Every Odoo extension that does this regrets it. `stock.quant.location_id`
already *is* the slot — we just need to make `location_id` resolve to a slot
record.

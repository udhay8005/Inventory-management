# 02 — Data model

## Core: location hierarchy on top of `stock.location`

We **extend** `stock.location` instead of inventing a new tree. This keeps
Odoo's quant/move machinery working unchanged.

```
stock.warehouse
    └─ stock.location (view, usage='view')      WH/Stock
        └─ stock.location (internal, type=rack)         WH/Stock/R-01
            └─ stock.location (internal, type=divider)  WH/Stock/R-01/D-1   ← exactly 6 per rack
                └─ stock.location (internal, type=slot) WH/Stock/R-01/D-1/S-1   ← exactly 3 per divider
```

### Fields added to `stock.location` (in `wms_location`)

| Field | Type | Notes |
|---|---|---|
| `wms_location_type` | Selection | `warehouse_view` / `rack` / `divider` / `slot` |
| `wms_rack_code` | Char | e.g. `R-01` (only on rack) |
| `wms_divider_number` | Integer | 1..6 (only on divider) |
| `wms_slot_number` | Integer | 1..3 (only on slot) |
| `wms_capacity_units` | Float | Soft cap shown in UI; not enforced like a hard lock |
| `wms_is_damage` | Boolean | This internal location holds damaged stock |
| `wms_is_repair` | Boolean | This internal location holds in-repair stock |

### Constraints (Python `@api.constrains`)

- A rack must have exactly 6 child dividers (warning, not crash, while being created — hard-error on save once "auto-generate slots" has been run).
- A divider must have exactly 3 child slots.
- `wms_divider_number` ∈ [1..6]; `wms_slot_number` ∈ [1..3].

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

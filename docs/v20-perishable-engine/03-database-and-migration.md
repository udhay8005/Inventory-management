# v20 Database Changes + Migration & Rollback

## 1. New dependency

`product_expiry` (Odoo standard module). Adds to `stock.lot`: `expiration_date`, `use_date`,
`removal_date`, `alert_date`; to `product.template`: `use_expiration_date`, `expiration_time`,
`use_time`, `removal_time`, `alert_time`. **Confirmed not currently installed.** v20 uses it for
the lot-level expiry data model only — the WMS keeps its own `_wms_sorted_for_removal` as the
single picker (it does **not** adopt Odoo's native FEFO removal strategy).

## 2. New / extended fields

### `stock.lot` (extend via `_inherit`)
| Field | Type | Notes |
|-------|------|-------|
| `expiration_date` | Date | from `product_expiry` (don't re-declare) |
| `wms_lot_state` | Selection | `available`(default)/`quarantine`/`recalled`/`destroyed`. NOT reserved (native), NOT expired (computed) |
| `wms_supplier_id` | Many2one res.partner | recall/traceability |
| `wms_supplier_batch` | Char | supplier's own batch code |
| `wms_supplier_invoice` | Char | inbound traceability |
| `wms_manufacture_date` | Date | optional |

### `stock.quant` (extend via `_inherit`)
| Field | Type | Notes |
|-------|------|-------|
| `wms_effective_expiry` | Date, **stored, indexed**, computed | `lot_id.expiration_date or product_id.product_tmpl_id.wms_expiry_date`; `@api.depends("lot_id.expiration_date","product_id.product_tmpl_id.wms_expiry_date")`. The one value the FEFO sort reads. |

### `stock.location` (extend via `_inherit`)
| Field | Type | Notes |
|-------|------|-------|
| `wms_is_quarantine` | Boolean | excluded from picker (like `wms_is_damage`) |
| `wms_is_recall` | Boolean | excluded from picker; holds physically-segregated recalled stock |

### `wms.scan.receipt.line` (extend transient via `_inherit`)
`batch_number` (Char), `expiry_date` (Date), `manufacture_date` (Date), `supplier_id` (M2o),
`supplier_batch` (Char), `supplier_invoice` (Char).

### `wms.issue.approval` + `.line` (extend via `_inherit`)
`reason_expired` (Boolean), `expired_product_id` (M2o), `expired_batch_name` (Char),
`expired_date` (Date). (`line.expiry_date` already exists.)

### `product.template` (extend via `_inherit`)
No new persistent field required. `create()` sets native `tracking='lot'` +
`use_expiration_date=True` for perishable kinds. `wms_expiry_date` stays as the non-lot fallback.

## 3. New models

- `wms.lot.recall` — persistent. `lot_id`(req), `product_id`(related, store), `supplier_id`,
  `recall_date`, `reason`(supplier/quality/regulatory), `description`, `state`
  (active/resolved/disposed), `action_required`. Active recall → set lot `wms_lot_state='recalled'`
  + notify managers. Unique active recall per lot.
- `wms.perishable.settings` — singleton-style config (or a set of `ir.config_parameter`):
  thresholds 180/90/60/30/15/7/expired; digest cadence; email flag; auto-quarantine-expired;
  disposal location.
- `wms.expiry.lot.ledger` — `_auto=False` SQL view: per-lot on-hand by location/rack/compartment,
  `expiration_date`, `days_to_expiry`, `on_hand/reserved/available`, `status`, `recall_status`;
  `_order="expiration_date asc"`.
- `wms.lot.traceability` — `_auto=False` SQL view: supplier→PO→lot→receipt→location→last keeper.
- `wms.expiry.alert` — **re-keyed** to `stock.lot.expiration_date` (fallback template); adds
  `lot_id`, `batch`, `recall_status`; thresholds from settings.

## 4. Indexes
- `idx_quant_fefo` on `stock_quant (product_id, wms_effective_expiry) WHERE quantity > 0`
  (created in `wms_perishable` post-init, mirroring `wms_fifo/hooks.py`'s `idx_quant_fifo`).
- `idx_stock_lot_expiry` on `stock_lot (product_id, expiration_date)` for the report views.
- Unique partial index for active recalls: `wms_lot_recall (lot_id) WHERE state='active'`.

## 5. The migration (the one sharp edge)

**Problem.** Odoo forbids switching a product to `tracking='lot'` while it has on-hand stock
(existing quants have `lot_id IS NULL`). v20 auto-enables tracking only on **new** products, so
existing perishable products keep `tracking='none'` until explicitly migrated.

**Three supported paths (pick per deployment):**

1. **Fresh DB / at go-live (cleanest, recommended).** v20 ships on a clean install; every
   perishable product is `tracking='lot'` from creation. No migration of live stock needed. This
   is why the roadmap puts v20 on a fresh v20 line after v19 cert.
2. **Per-product at zero stock.** Operator zeroes a product's on-hand (consume/transfer), then a
   small wizard flips `tracking='lot'`. Safe, gradual, no SQL.
3. **Legacy-lot migration (bulk, for a populated DB).** A versioned migration assigns existing
   on-hand quants to a per-product "legacy" lot so tracking can be enabled without orphaning
   history. Template (idempotent, logged), modelled on `wms_barcode/migrations/19.0.1.7.0`:

```
# pre-migration.py  (runs before the ORM touches schema)
#  - create one LEGACY-<YYYYMMDD>-<product_id> stock.lot per perishable product that has on-hand
#  - assign every on-hand quant of those products to its legacy lot (UPDATE ... WHERE lot_id IS NULL)
#  - then it is safe to set tracking='lot' on those products
# post-migration.py
#  - backfill stock_move_line.lot_id from the quant's legacy lot (history continuity)
#  - ANALYZE / index refresh
```

Legacy lots carry **no** expiration_date (the FEFO sort falls back to the template
`wms_expiry_date` for them, then `in_date` — i.e., they behave like today's FIFO until consumed).
New receipts going forward carry real per-lot expiries.

**Hard rule:** never flip `tracking` on live non-zero stock outside paths 2 or 3.

## 6. Rollback

- The new module is **additive** — uninstalling `wms_perishable` removes its models, views,
  fields, crons, locations, and the FEFO override; v19 behaviour returns (FIFO on the template
  expiry). The legacy lots remain harmless (lots with no expiry).
- The migration is **reversible only by restore**: once `tracking='lot'` is set and quants carry
  lots, downgrading to `tracking='none'` with stock on hand is blocked by Odoo. Therefore the
  migration runs **only** after a verified backup, and the rollback for path 3 is **restore the
  pre-migration backup** (the project's `restore-native.ps1`). Document the exact backup file in
  the migration run log.
- Provide a `wms.perishable.uninstall` checklist: stop services → back up → uninstall module →
  (if needed) restore. Tested in CI's fresh-install + upgrade jobs.

## 7. Constraints preserved (unaffected)
SKU `UNIQUE(default_code)`, PRD `UNIQUE(wms_product_code)`, barcode uniqueness, the SKU/barcode
composition, and the duplicate-identity block all stay intact — lot tracking is orthogonal to
product identity. Verified: the create() SKU/barcode path does not change.

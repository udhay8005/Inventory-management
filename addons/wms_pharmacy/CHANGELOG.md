# Changelog — wms_pharmacy (v20 Wave 3: Pharmacy Packaging Engine)

## 19.0.3.0.0 — Wave 3 (branch `v20-wave2-3`) — 2026-06-27

First release of the pharmacy packaging engine. Additive over Wave 1/2 —
depends on `wms_perishable` (lots / expiry / animal / FEFO) and `wms_barcode`
(scanning). No existing addon is edited except additive `_inherit` of
`product.template` and `wms.animal`.

Full `wms_pharmacy` suite: **29 tests, 0 failed / 0 error**; black / isort /
flake8 clean.

### Added

- **Packaging hierarchy** on `product.template`: `wms_is_packaged`,
  `wms_tablets_per_strip`, `wms_strips_per_box`, computed `wms_tablets_per_box`,
  with a consistency constraint and a "Pharmacy packaging" group on the product
  form.
- **Nested packaging barcodes** (`wms.pharma.packaging.barcode`): one barcode
  per tier (box / strip / tablet) resolving to the product + base tablet count,
  with a `resolve()` lookup and cross-namespace collision guard.
- **Open-strip / partial-strip tracking** (`wms.open.strip`): loose tablets
  broken out of a sealed strip, per product / lot / location.
- **Dispensing engine** (`wms.dispense.wizard`): dispenses tablets with
  **strip-level FEFO** (earliest-expiry available lot), **open-package
  optimisation** (draw from an already-open strip before breaking a sealed one),
  opening new strips as needed and recording how many; deducts stock via a real
  DONE outbound `stock.move`; blocks zero / insufficient / non-available stock.
- **Pharmaceutical genealogy** (`wms.dispense.log`): one row per dispense
  capturing product / lot / animal / quantity / strips-opened / per-strip &
  per-box snapshots — the box → strip → tablet → dose lineage and the
  medication-history record.
- **Animal medication history**: `wms.animal` gains `dispense_log_ids` +
  `wms_medication_count` + a smart button / history page.

Menus live under WMS ▸ Pharmacy; ACLs gate manager vs user access.

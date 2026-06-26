# wms_perishable — Universal Perishable Engine (v20 Wave 1)

Per-lot expiry, FEFO, and lifecycle control for the Dakshin Vrindavan gaushala
WMS. An **additive** layer over the frozen v19 addons — every change is an
`_inherit` extension or a new model; no v19 file is edited.

## Implemented (Wave 1)

| Area | Tickets |
|------|---------|
| New perishable kinds (vaccine/supplement/chemical/fertilizer/food) | V20-002 |
| Lot-tracked perishables (auto `tracking='lot'` + expiry on create) | V20-003 |
| Lot-aware Scan Receipt (batch/expiry/supplier, find-or-create lot) | V20-004/005 |
| `stock.lot` lifecycle + supplier/expiry metadata | V20-007 |
| Stored+indexed `stock.quant.wms_effective_expiry` (+ `idx_quant_fefo`) | V20-008 |
| Per-lot FEFO removal (overrides `_wms_sorted_for_removal` only) + auto-split | V20-009 |
| Per-lot expiry/batch/resulting-balance on the issue plan | V20-010 |
| Expired stock blocked from issue + shortfall reason | V20-011a |
| Manager override to issue expired (audited) | V20-011b |
| Disposal carve-out (expired stock stays damageable) | V20-011c |
| Lot-aware issue reversal (restores the original lot) | V20-012 |
| Lot recall (freeze + unreserve + release) | V20-013 |
| Lot quarantine (hold / release / reject / destroy) | V20-014 |
| Per-lot expiry report (owner thresholds) | V20-015 |
| Lot barcode label (print + scan-back) | V20-016 |
| Lot timeline + lifecycle on the lot form | V20-017 |
| Near-expiry receiving guard (manager override) | V20-018 |
| Stable extension hook API | V20-019 |

The full frozen design lives in
[`../../docs/v20-perishable-engine/`](../../docs/v20-perishable-engine/).

## Extension Hook API (v20 Hook API 1.0)

Downstream modules extend perishable behaviour through one stable, versioned
extension point — **without** touching the FEFO / recall / quarantine
internals. Override `stock.lot._wms_lifecycle_hook` and switch on the event.

```python
from odoo import models


class StockLot(models.Model):
    _inherit = "stock.lot"

    def _wms_lifecycle_hook(self, event, payload=None):
        res = super()._wms_lifecycle_hook(event, payload)  # keep the chain
        if event == "recalled":
            # `self` = the recalled lots; `payload` = the wms.lot.recall record.
            self._notify_supplier_quality(payload)
        elif event == "received":
            # `payload` = the wms.scan.receipt.line that received the batch.
            self._feed_expiry_risk_model()
        return res
```

### Events (`WMS_LIFECYCLE_EVENTS`)

| Event | Fired when | `payload` |
|-------|-----------|-----------|
| `received` | a batch is received onto the shelf | `wms.scan.receipt.line` |
| `issued` | a batch is issued out | `stock.picking` (the issue) |
| `recalled` | a lot is recalled (frozen) | `wms.lot.recall` |
| `quarantined` | a lot is put on QC hold | `wms.lot.quarantine` |
| `released` | a recall/quarantine is released to available | the recall / quarantine record |
| `rejected` | a QC hold is rejected | `wms.lot.quarantine` |
| `destroyed` | a lot is marked destroyed | `wms.lot.quarantine` |

`self` is always the affected `stock.lot` recordset. The base implementation is
a no-op, so unhandled events are safe. `WMS_HOOK_API_VERSION` (`"1.0"`) is
exported from `wms_perishable.models.stock_lot` for modules pinning the vocabulary.

## Configuration

* `wms_perishable.min_receive_shelf_life_days` (default `60`) — minimum shelf
  life a perishable must have left to be received without a manager override
  (V20-018). Set to `0` to disable the near-expiry receiving guard.

## Design invariants (carried from Phase-0)

1. FEFO reads the **stored+indexed** `stock.quant.wms_effective_expiry` (never a
   per-quant traversal) — `idx_quant_fefo` serves the scan.
2. New perishable products auto-enable `tracking='lot'`; existing stock migrates
   via the legacy-lot path at zero stock / go-live.
3. Override `_wms_sorted_for_removal` **only**, never `_gather` (wms_fifo owns
   `_gather`; the MRO picks up the v20 sort, which stays a pure ordering
   function — exclusion lives in the issue planner / gather domain).

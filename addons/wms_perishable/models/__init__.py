from . import product_template  # V20-002 kinds; V20-003 auto-enable lot+expiry
from . import scan_issue  # V20-010: per-lot expiry + resulting-balance on the issue plan
from . import stock_location  # V20-011: exclude expired lots from the issue plan
from . import stock_lot  # V20-007: lot lifecycle + supplier/expiry metadata
from . import stock_picking  # V20-012: lot-aware issue reversal (restore the original lot)
from . import stock_quant  # V20-008: stored+indexed wms_effective_expiry (FEFO sort key)
from . import wms_damage  # V20-011c: disposal carve-out — damage can move expired stock
from . import wms_lot_expiry_alert  # V20-015: per-lot expiry report (SQL view)
from . import wms_lot_migration  # V20-020: legacy -> lot-tracking migration wizard
from . import wms_lot_quarantine  # V20-014: QC hold + release/reject/destroy
from . import wms_lot_recall  # V20-013: recall freeze + unreserve + release
from . import wms_shelf_life_policy  # V20-022: per-kind shelf-life table
from . import wms_shelf_life_settings  # V20-022: global shelf-life fallback settings
from . import (  # V20-004/005: lot-aware receipt (batch/expiry/supplier, find-or-create lot)
    scan_receipt,
)

# Wave 1 models continue here, per the frozen spec in docs/v20-perishable-engine/.
# Each module is added to the `from . import ...` list above as its ticket lands.

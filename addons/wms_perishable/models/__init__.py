from . import product_template  # V20-002 kinds; V20-003 auto-enable lot+expiry
from . import scan_issue  # V20-010: per-lot expiry + resulting-balance on the issue plan
from . import stock_lot  # V20-007: lot lifecycle + supplier/expiry metadata
from . import stock_quant  # V20-008: stored+indexed wms_effective_expiry (FEFO sort key)
from . import (  # V20-004/005: lot-aware receipt (batch/expiry/supplier, find-or-create lot)
    scan_receipt,
)

# Wave 1 models continue here, per the frozen spec in docs/v20-perishable-engine/.
# Planned (NOT yet implemented):
#   - wms_lot_recall.py   : supplier/manual recall + RECALL-ACTIVE freeze.
#   - quarantine          : reuse the wms_is_* picker-exclusion pattern.
#   - product_template.py : per-kind shelf-life table + near-expiry guards.
#   - res_config / settings, per-lot reports, dashboard.
#
# Each module is added to the `from . import ...` list below as its ticket lands.

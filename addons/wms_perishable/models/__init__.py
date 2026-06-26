from . import product_template  # V20-002: new perishable kinds
from . import stock_lot  # V20-007: lot lifecycle + supplier/expiry metadata

# Wave 1 models continue here, per the frozen spec in docs/v20-perishable-engine/.
# Planned (NOT yet implemented):
#   - stock_quant.py      : stored+indexed wms_effective_expiry (lot->template
#                           fallback) + idx_quant_fefo; FEFO override on
#                           _wms_sorted_for_removal ONLY (never _gather).
#   - stock_lot.py        : lot lifecycle (states, manufacture date, supplier ref).
#   - wms_lot_recall.py   : supplier/manual recall + RECALL-ACTIVE freeze.
#   - quarantine          : reuse the wms_is_* picker-exclusion pattern.
#   - product_template.py : per-kind shelf-life table + near-expiry guards.
#   - res_config / settings, per-lot reports, dashboard.
#
# Each module is added to the `from . import ...` list below as its ticket lands.

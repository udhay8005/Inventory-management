from . import stock_lot  # W2 #10: lot audit / completeness score
from . import wms_bulk_ops  # W2 #13: bulk recall/quarantine/destroy server actions
from . import wms_cold_chain  # W2 #12: cold-chain temperature readings + hold
from . import wms_cycle_count_priority  # W2 #14: cycle-count risk prioritisation (SQL view)
from . import wms_disposal_report  # W2 #5: disposal / loss analytics (SQL view)
from . import wms_fefo_compliance  # W2 #7: FEFO compliance of Scan Issues (SQL view)
from . import wms_forecast_risk  # W2 #3: forecast weekly avg + overstock/understock risk
from . import wms_ledgers  # W2 #8: lot / product / warehouse ledgers (SQL views)
from . import wms_links  # W2 #4: supplier links on damage / quarantine
from . import wms_lot_expiry_risk  # W2 #2: expiry-risk engine (SQL view)
from . import wms_lot_traceability  # W2 #15: end-to-end lot traceability (SQL view)
from . import wms_occupancy_snapshot  # W2 #7: occupancy-over-time stored snapshots + cron
from . import wms_recall_dashboard  # W2 #9: recall dashboard aggregates (_inherit)
from . import wms_stock_health  # W2 #6: stock health score (SQL view)
from . import wms_supplier_scorecard  # W2 #4: supplier scorecard + ledger (SQL views)
from . import wms_usage_reports  # W2 #8: department / animal / medicine usage (SQL views)

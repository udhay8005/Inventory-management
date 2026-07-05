{
    "name": "WMS — Offline AI Forecasting",
    "version": "19.0.1.6.0",
    "summary": "Per-product demand forecasting (Holt-Winters / SES) + deterministic reorder math.",
    # wms_barcode supplies the Scan-Issue flags (wms_is_scan_issue,
    # wms_reversed_by_id) the consumption query in _gather_outflow reads,
    # so the forecast engine now depends on it.
    "depends": ["wms_location", "wms_barcode", "stock", "purchase"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "external_dependencies": {
        "python": ["statsmodels", "pandas", "numpy"],
    },
    "data": [
        "security/wms_forecast_security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/wms_forecast_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}

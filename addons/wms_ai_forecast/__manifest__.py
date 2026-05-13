{
    "name": "WMS — Offline AI Forecasting",
    "version": "19.0.1.0.0",
    "summary": "Per-product demand forecasting (Holt-Winters / SES) + deterministic reorder math.",
    "depends": ["wms_location", "stock", "purchase"],
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

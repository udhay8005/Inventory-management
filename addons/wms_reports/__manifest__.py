{
    "name": "WMS — Reports & Dashboards",
    "version": "19.0.1.0.0",
    "summary": "Live SQL-view dashboards: oldest stock, occupancy, dead stock, reorder summary.",
    "depends": ["wms_location", "wms_ai_forecast", "wms_repair_damage", "stock"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "views/wms_oldest_stock_views.xml",
        "views/wms_occupancy_views.xml",
        "views/wms_reorder_summary_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}

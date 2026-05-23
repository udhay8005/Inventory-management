{
    "name": "WMS — Reports & Dashboards",
    "version": "19.0.1.0.1",
    "summary": "Live SQL-view dashboards: oldest stock, occupancy, dead stock, reorder summary.",
    "depends": ["wms_location", "wms_ai_forecast", "wms_repair_damage", "stock"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        # View files first (they define the actions referenced by menus.xml).
        "views/wms_oldest_stock_views.xml",
        "views/wms_occupancy_views.xml",
        "views/wms_reorder_summary_views.xml",
        "views/wms_product_stock_views.xml",
        "views/wms_movement_history_views.xml",
        "views/wms_cycle_count_views.xml",
        "views/wms_tool_fleet_summary_views.xml",
        "views/wms_storekeeper_activity_views.xml",
        "views/wms_expiry_alert_views.xml",
        "views/wms_audit_views.xml",
        "views/rack_grid_template.xml",
        "views/rack_form_inherit.xml",
        "views/warehouse_map_template.xml",
        # menus.xml LAST so every action ref already exists. The menu under
        # menu_wms_reports_root for cycle-count-due lives here too rather
        # than inside its view file.
        "views/menus.xml",
        "data/cron.xml",
    ],
    "installable": True,
}

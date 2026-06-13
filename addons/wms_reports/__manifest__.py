{
    "name": "WMS — Reports & Dashboards",
    "version": "19.0.4.2.0",
    "summary": "Live SQL-view dashboards + backup/DR observability (health endpoint, backup audit).",
    "depends": ["wms_location", "wms_ai_forecast", "wms_repair_damage", "stock"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        # Groups first: the ACL csv below references group_wms_backup_now.
        "security/gdrive_security.xml",
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
        # Loaded after menus.xml: its menuitem is parented to menu_wms_reports_root.
        "views/wms_backup_audit_views.xml",
        "views/wms_self_diagnostics_views.xml",
        # Parented to menu_wms_reports_root -> load after menus.xml.
        "views/dashboard_template.xml",
        # Menus parented to menu_wms_reports_root + reuses the activity search
        # view defined earlier -> load after menus.xml.
        "views/wms_value_reports_views.xml",
        # Returns-due report (F3): menu parented to menu_wms_reports_root ->
        # load after menus.xml.
        "views/wms_returns_due_views.xml",
        # Menu parented to wms_location.menu_wms_operations (a dependency).
        "views/find_template.xml",
        # Google Drive backup surfaces: Backup Now wizard (menu under the
        # WMS root, gated by group_wms_backup_now), restore browser +
        # settings wizard (manager-only, under wms_location.menu_wms_config).
        # Self-contained actions/menus -> only needs the security groups.
        "views/wms_gdrive_views.xml",
        # Seeded wms_gdrive.* configuration parameters (noupdate).
        "data/gdrive_params.xml",
        # Seeded wms_reports.default_return_days fallback SLA (F3, noupdate).
        "data/wms_returns_params.xml",
        "data/cron.xml",
    ],
    "installable": True,
}

{
    "name": "WMS — Barcode scan & print",
    "version": "19.0.1.53.0",
    "summary": "Receive/Issue scan wizards, carton aliases, label printing.",
    "depends": ["wms_location", "wms_fifo", "stock", "barcodes", "mail"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        # Groups first: the approve-capability group is referenced by the
        # approval views below, and is implied into group_wms_manager here.
        "security/wms_approval_security.xml",
        "security/ir.model.access.csv",
        # Approval-gate params + the held-issue sequence (F4 + F5).
        "data/wms_approval_params.xml",
        # Fuel-log sequence.
        "data/wms_fuel_data.xml",
        # Direct-print: seed the thermal printer profile (noupdate).
        "data/wms_label_printer_data.xml",
        "views/wms_barcode_alias_views.xml",
        "views/wms_storekeeper_views.xml",
        "views/wms_label_config_views.xml",
        "views/wms_label_printer_views.xml",
        "views/stock_picking_views.xml",
        "views/wms_issue_approval_views.xml",
        "wizards/scan_receipt_views.xml",
        "wizards/scan_issue_views.xml",
        "wizards/wms_label_print_wizard_views.xml",
        "wizards/wms_product_onboard_views.xml",
        "wizards/wms_product_create_views.xml",
        "reports/thermal_label_report.xml",
        "reports/thermal_label_template.xml",
        "views/wms_fuel_log_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "wms_barcode/static/src/scss/scan_wizard.scss",
        ],
    },
    "installable": True,
}

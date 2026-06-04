{
    "name": "WMS — Barcode scan & print",
    "version": "19.0.1.15.0",
    "summary": "Receive/Issue scan wizards, carton aliases, label printing.",
    "depends": ["wms_location", "wms_fifo", "stock", "barcodes", "mail"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "data/wms_barcode_data.xml",
        "views/wms_barcode_alias_views.xml",
        "views/wms_storekeeper_views.xml",
        "views/wms_label_config_views.xml",
        "views/stock_picking_views.xml",
        "wizards/scan_receipt_views.xml",
        "wizards/scan_issue_views.xml",
        "wizards/wms_product_onboard_views.xml",
        "reports/thermal_label_report.xml",
        "reports/thermal_label_template.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "wms_barcode/static/src/scss/scan_wizard.scss",
        ],
    },
    "installable": True,
}

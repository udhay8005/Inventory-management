{
    "name": "WMS — Barcode scan & print",
    "version": "19.0.1.0.0",
    "summary": "Receive/Issue scan wizards, carton aliases, label printing.",
    "depends": ["wms_location", "wms_fifo", "stock", "barcodes"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "views/wms_barcode_alias_views.xml",
        "wizards/scan_receipt_views.xml",
        "wizards/scan_issue_views.xml",
        "reports/barcode_label_report.xml",
        "reports/barcode_label_template.xml",
        "views/menus.xml",
    ],
    "installable": True,
}

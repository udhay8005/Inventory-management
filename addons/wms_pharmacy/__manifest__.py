# File: __manifest__.py
# Module: wms_pharmacy
# Description: Wave 3 — Pharmacy packaging engine for Dakshin Vrindavan Gaushala WMS.
#              Box→Strip→Tablet hierarchy, FEFO dispensing, open-strip tracking,
#              pharmaceutical genealogy logs, and animal medication history.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: wms_perishable, wms_barcode
{
    "name": "WMS — Pharmacy packaging engine",
    "version": "19.0.3.0.0",
    "summary": "Box→Strip→Tablet packaging, FEFO dispensing, open-strip tracking, genealogy logs.",
    "description": """
Wave 3 — Pharmacy Packaging Engine
====================================
* Packaging hierarchy on product (Box > Strip > Tablet) with computed tablets_per_box.
* Packaging barcodes: one barcode per tier resolves to product + base_units.
* Open-strip / partial-strip tracker: loose tablets broken out of sealed strips.
* Dispense wizard: strip-level FEFO, open-package optimisation, real DONE stock.move.
* Pharmaceutical genealogy log (wms.dispense.log): box→strip→tablet→dose traceability.
* Animal medication history: smart button + notebook page on wms.animal.
    """,
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "depends": ["wms_perishable", "wms_barcode"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
        "views/wms_pharma_packaging_barcode_views.xml",
        "views/wms_open_strip_views.xml",
        "views/wms_dispense_log_views.xml",
        "wizards/wms_dispense_wizard_views.xml",
        "views/wms_animal_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}

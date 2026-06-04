{
    "name": "WMS — Damage, Repair, Return",
    "version": "19.0.1.6.0",
    "summary": "Damage / repair / return workflows that generate auditable stock moves.",
    "depends": ["wms_location", "wms_barcode", "stock", "mail"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/wms_repair_security.xml",
        "security/ir.model.access.csv",
        "data/locations.xml",
        "views/wms_damage_views.xml",
        "views/wms_repair_order_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_locations",
    "installable": True,
}

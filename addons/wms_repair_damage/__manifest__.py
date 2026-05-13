{
    "name": "WMS — Damage, Repair, Return",
    "version": "19.0.1.0.0",
    "summary": "Damage / repair / return workflows that generate auditable stock moves.",
    "depends": ["wms_location", "stock", "mail"],
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "data": [
        "security/ir.model.access.csv",
        "security/wms_repair_security.xml",
        "data/locations.xml",
        "views/wms_damage_views.xml",
        "views/wms_repair_order_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_locations",
    "installable": True,
}

{
    "name": "WMS — Location (Rack/Divider/Slot)",
    "version": "19.0.1.0.0",
    "summary": "Model warehouse storage as Rack → 6 Dividers → 3 Slots on top of stock.location",
    "description": """
WMS Location
============
Extends `stock.location` with a Rack / Divider / Slot hierarchy. Each rack
holds exactly 6 dividers, each divider exactly 3 slots. Quants stay in
`stock.quant` so Odoo's standard movement, valuation, and FIFO logic
keep working unchanged.

Key features:
* `wms_location_type` discriminator on `stock.location`.
* Constraints: 6 dividers / rack, 3 slots / divider.
* `wms.rack.generator` wizard to spin up a rack with all slots in one click.
* Search/tree/kanban views for slot occupancy.
""",
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "depends": ["stock", "barcodes", "mail"],
    "data": [
        "security/wms_security.xml",
        "security/ir.model.access.csv",
        "views/stock_location_views.xml",
        "views/wms_rack_generator_views.xml",
        "views/wms_floor_zone_generator_views.xml",
        "views/wms_zone_generator_views.xml",
        "views/menus.xml",
        "data/wms_data.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "application": True,
    "installable": True,
}

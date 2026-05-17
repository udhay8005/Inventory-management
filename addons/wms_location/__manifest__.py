{
    "name": "WMS — Location (Rack / Compartment / Slot)",
    "version": "19.0.2.1.0",
    "summary": "Model warehouse storage as Rack → Compartment (multi-shelf-spannable) → Slot on top of stock.location",
    "description": """
WMS Location
============
Extends `stock.location` with a Rack / Compartment / Slot hierarchy. Each
rack has its own freely configurable shelf and column count. Compartments
can span multiple shelves (e.g. one tall compartment covering shelves
1-3 for bottles) and can be sub-divided into any number of slots. Quants
stay in `stock.quant` so Odoo's standard movement, valuation, and FIFO
logic keep working unchanged.

Key features:
* `wms_location_type` discriminator on `stock.location`.
* Visual OWL-based Rack Builder with live grid preview, click-to-merge
  cells vertically, per-compartment slot count.
* Per-rack flexible shelf_count / column_count — no hard caps.
* `wms.rack.generator` wizard (quick-grid + custom layout JSON).
* Search/tree/kanban views for slot occupancy.
* Barcode format: <rack_code>-SH<top>[-<bottom>]-C<col>-SL<slot>
""",
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "depends": ["stock", "barcodes", "mail", "web"],
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
    "assets": {
        "web.assets_backend": [
            "wms_location/static/src/components/rack_builder/rack_builder.js",
            "wms_location/static/src/components/rack_builder/rack_builder.xml",
            "wms_location/static/src/components/rack_builder/rack_builder.scss",
        ],
    },
    "application": True,
    "installable": True,
}

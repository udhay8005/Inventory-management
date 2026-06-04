{
    "name": "WMS — Location (Rack / Compartment / Slot)",
    "version": "19.0.3.3.0",
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
    "depends": ["barcodes", "mail", "product", "stock", "web"],
    "data": [
        "security/wms_security.xml",
        "security/ir.model.access.csv",
        "views/stock_location_views.xml",
        "views/product_product_views.xml",
        "views/wms_rack_generator_views.xml",
        "views/wms_floor_zone_generator_views.xml",
        "views/wms_zone_generator_views.xml",
        "views/menus.xml",
        "views/favicon_override.xml",
        "views/branding_head.xml",
        "views/login_layout_override.xml",
        "views/backup_menus.xml",
        "data/wms_data.xml",
        "data/wms_sku_sequences.xml",
        "data/wms_barcode_actions.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # Brand skin first so component SCSS picks up the new
            # CSS variables (--o-brand-primary etc.) when it loads.
            "wms_location/static/src/scss/wms_branding.scss",
            "wms_location/static/src/components/rack_builder/rack_builder.js",
            "wms_location/static/src/components/rack_builder/rack_builder.xml",
            "wms_location/static/src/components/rack_builder/rack_builder.scss",
        ],
        # Loaded on /web/login. Patches UserSwitch to drop `admin`
        # from the "Choose a user" picker so privileged logins are
        # not advertised on the login page, plus paints the form in
        # the trust's saffron palette.
        "web.assets_frontend": [
            "wms_location/static/src/scss/wms_login_branding.scss",
            "wms_location/static/src/js/hide_admin_from_user_switch.js",
        ],
    },
    "application": True,
    "installable": True,
}

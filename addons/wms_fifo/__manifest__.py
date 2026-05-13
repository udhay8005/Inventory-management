{
    "name": "WMS — Global FIFO",
    "version": "19.0.1.0.0",
    "summary": "FIFO removal across all slots under the warehouse stock location.",
    "description": """
Overrides `stock.quant._gather` ordering so that pick lines automatically pull
the oldest `in_date` quants first regardless of which slot they live in.

Adds a partial index on (product_id, in_date) WHERE quantity>0 for fast
FIFO scans on large quant tables.
""",
    "author": "WMS",
    "license": "LGPL-3",
    "category": "Inventory/Warehouse",
    "depends": ["wms_location"],
    "data": [
        "data/post_init.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}

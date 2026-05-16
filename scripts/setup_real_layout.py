"""Real-world layout: 1st Floor (32 racks) + Ground Floor East/West (floor zones)."""

Loc = env["stock.location"]
wh = env["stock.warehouse"].search([], limit=1)
stock_root = wh.lot_stock_id

# 1. Create 1st Floor zone, move all 32 racks into it.
first_floor = Loc.search(
    [
        ("location_id", "=", stock_root.id),
        ("name", "=", "1st Floor"),
    ],
    limit=1,
)
if not first_floor:
    first_floor = Loc.create(
        {
            "name": "1st Floor",
            "location_id": stock_root.id,
            "company_id": stock_root.company_id.id,
            "usage": "view",
            "wms_location_type": "zone",
        }
    )

# Reparent all racks that aren't already under 1st Floor
racks = Loc.search([("wms_location_type", "=", "rack")])
to_move = racks.filtered(lambda r: r.location_id != first_floor)
to_move.write({"location_id": first_floor.id})
print(f"1st Floor: {len(racks)} racks (moved {len(to_move)})")

# 2. Ground Floor with East + West sub-zones.
ground = Loc.search(
    [
        ("location_id", "=", stock_root.id),
        ("name", "=", "Ground Floor"),
    ],
    limit=1,
)
if not ground:
    ground = Loc.create(
        {
            "name": "Ground Floor",
            "location_id": stock_root.id,
            "company_id": stock_root.company_id.id,
            "usage": "view",
            "wms_location_type": "zone",
        }
    )

for side, count in (("East", 6), ("West", 6)):
    sub = Loc.search(
        [
            ("location_id", "=", ground.id),
            ("name", "=", side),
        ],
        limit=1,
    )
    if not sub:
        sub = Loc.create(
            {
                "name": side,
                "location_id": ground.id,
                "company_id": ground.company_id.id,
                "usage": "view",
                "wms_location_type": "zone",
            }
        )
    # Generate floor zones under each side
    existing = Loc.search_count(
        [
            ("location_id", "=", sub.id),
            ("wms_location_type", "=", "floor"),
        ]
    )
    to_create = max(0, count - existing)
    if to_create:
        gen = env["wms.floor.zone.generator"].create(
            {
                "warehouse_id": wh.id,
                "parent_location_id": sub.id,
                "zone_prefix": f"GF-{side[0]}",  # e.g. GF-E, GF-W
                "count": to_create,
                "start_number": existing + 1,
                "capacity_units": 500,
            }
        )
        gen.action_generate()
    print(f"Ground Floor / {side}: {count} floor zones (created {to_create} new)")

# Also move existing F-01..F-05 (under stock_root) into Ground Floor East
loose_floors = Loc.search(
    [
        ("location_id", "=", stock_root.id),
        ("wms_location_type", "=", "floor"),
    ]
)
if loose_floors:
    east = Loc.search([("location_id", "=", ground.id), ("name", "=", "East")], limit=1)
    loose_floors.write({"location_id": east.id})
    print(f"Moved {len(loose_floors)} loose floor zones into Ground Floor / East")

env.cr.commit()

# Summary
env.cr.execute(
    """
    SELECT wms_location_type, COUNT(*) FROM stock_location
     WHERE wms_location_type IS NOT NULL
     GROUP BY wms_location_type ORDER BY 1;
"""
)
print("\nFinal counts:")
for row in env.cr.fetchall():
    print(f"  {row[0]:10s} {row[1]}")

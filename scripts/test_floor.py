"""Smoke-test the new floor / non-rack storage."""

# 1. Generate 5 floor zones
wh = env["stock.warehouse"].search([], limit=1)
gen = env["wms.floor.zone.generator"].create(
    {
        "warehouse_id": wh.id,
        "parent_location_id": wh.lot_stock_id.id,
        "zone_prefix": "F",
        "count": 5,
        "start_number": 1,
        "capacity_units": 200,
    }
)
gen.action_generate()
env.cr.commit()

zones = env["stock.location"].search([("wms_location_type", "=", "floor")])
print(f"Floor zones created: {len(zones)}")
for z in zones:
    print(f"  - {z.name}  barcode={z.barcode}")

# 2. Drop some demo stock into one of them
product = env["product.product"].search([("default_code", "=", "SCRW-M4-20")], limit=1)
if product and zones:
    target = zones[0]
    env["stock.quant"].create(
        {
            "product_id": product.id,
            "location_id": target.id,
            "quantity": 5000,
            "in_date": "2025-12-01 09:00:00",
        }
    )
    env.cr.commit()
    print(f"\nDropped 5000 screws into {target.name} ({target.barcode})")

# 3. Verify it shows in the product stock report
env.cr.execute(
    """
    SELECT pp.default_code, sl.name AS location, sl.wms_location_type AS kind,
           wpsr.quantity, wpsr.age_days, wpsr.is_oldest
      FROM wms_product_stock_report wpsr
      JOIN product_product pp ON pp.id = wpsr.product_id
      JOIN stock_location sl  ON sl.id = wpsr.location_id
     WHERE pp.default_code = 'SCRW-M4-20'
     ORDER BY wpsr.in_date;
"""
)
print("\nWhere is SCRW-M4-20?")
for row in env.cr.fetchall():
    print(
        f"  {row[0]:14s} {row[1]:8s} kind={row[2]:6s} qty={row[3]:7.0f} age={row[4]}d oldest={row[5]}"
    )

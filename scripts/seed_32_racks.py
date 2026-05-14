"""Generate racks R-01 through R-32 if they don't already exist.

Each rack = 6 levels × 4 dividers × 3 slots = 72 slots, so this brings the
total to 2,304 slots.
"""
import time

Location = env["stock.location"]
wh = env["stock.warehouse"].search([], limit=1)
parent = wh.lot_stock_id
existing = {r.wms_rack_code for r in Location.search([("wms_location_type", "=", "rack")])}

start = time.time()
created = 0
for n in range(1, 33):
    code = f"R-{n:02d}"
    if code in existing:
        continue
    gen = env["wms.rack.generator"].create({
        "rack_code": code,
        "parent_location_id": parent.id,
        "dividers_per_level": 4,
        "capacity_per_slot": 100,
    })
    gen.action_generate()
    created += 1
    if created % 4 == 0:
        env.cr.commit()
        print(f"  ... {created} new racks generated, elapsed {time.time()-start:.1f}s")

env.cr.commit()

env.cr.execute("""
    SELECT wms_location_type, COUNT(*) FROM stock_location
     WHERE wms_location_type IS NOT NULL
     GROUP BY wms_location_type ORDER BY 1;
""")
print("Final counts:")
for row in env.cr.fetchall():
    print(f"  {row[0]:10s} {row[1]}")
print(f"Total new racks created: {created}")
print(f"Total time: {time.time()-start:.1f}s")

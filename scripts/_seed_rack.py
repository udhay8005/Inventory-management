gen = env["wms.rack.generator"].create({
    "rack_code": "R-01",
    "parent_location_id": env["stock.warehouse"].search([], limit=1).lot_stock_id.id,
    "dividers_per_level": 4,
    "capacity_per_slot": 100,
})
gen.action_generate()
env.cr.commit()
print("Rack created")

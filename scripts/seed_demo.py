"""One-off: invoke the demo seeder against the wms DB.

Usage from host:
  docker compose exec odoo bash -c \
    "odoo shell -d wms --db_host=db --db_user=odoo --db_password=odoo_local_dev_pw \
                       --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
                       --no-http < /mnt/extra-addons/../scripts/seed_demo.py"

Or simply:
  docker compose exec odoo odoo shell -d wms \
    --db_host=db --db_user=odoo --db_password=odoo_local_dev_pw \
    --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
    --no-http
  >>> exec(open('/scripts/seed_demo.py').read())   # if mounted
"""

rack = env["stock.location"].search([("wms_location_type", "=", "rack")], limit=1)
seeder = env["wms.demo.seeder"].create({"rack_id": rack.id, "add_stock": True})
seeder.action_seed()
env.cr.commit()
print("Seeded products:", env["product.product"].search_count([("barcode", "like", "8901111%")]))
print(
    "Quants on slots:",
    env["stock.quant"].search_count(
        [("location_id.wms_location_type", "=", "slot"), ("quantity", ">", 0)]
    ),
)
print("Carton aliases:", env["wms.barcode.alias"].search_count([]))

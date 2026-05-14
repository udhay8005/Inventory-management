def post_init_locations(env):
    """Auto-create Damage / Repair-Out internal locations under every WH."""
    Loc = env["stock.location"]
    for wh in env["stock.warehouse"].search([]):
        view_loc = wh.view_location_id
        for name, flag in (("Damage", "wms_is_damage"), ("Repair-Out", "wms_is_repair")):
            existing = Loc.search([
                ("location_id", "=", view_loc.id),
                ("name", "=", name),
            ], limit=1)
            if not existing:
                Loc.create({
                    "name": name,
                    "location_id": view_loc.id,
                    "usage": "internal",
                    "company_id": view_loc.company_id.id,
                    flag: True,
                })

from odoo import api, fields, models


class WmsZoneGenerator(models.TransientModel):
    """Create a Zone (a parent view location) plus its contents in one click.

    Typical uses:
      - "1st Floor"  with 32 racks inside
      - "Ground Floor / East"  with 20 floor zones inside
      - "Outside Yard"  with a mix of racks and pallet areas

    The zone itself is a `stock.location` with usage='view' and
    `wms_location_type='zone'`. Racks/floors generated underneath behave
    identically to those generated directly under WH/Stock — same scan,
    FIFO, reports.

    For racks we delegate to wms.rack.generator's quick-grid mode: every
    rack created here uses the same shelf_count × column_count. Use the
    visual Rack Builder for one-off racks with custom layouts.
    """

    _name = "wms.zone.generator"
    _description = "Generate a Zone with racks and/or floor areas"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda s: s.env["stock.warehouse"].search([], limit=1),
    )
    parent_location_id = fields.Many2one(
        "stock.location",
        string="Parent location",
        required=True,
        help="Where the new zone will live. Usually the main warehouse stock location.",
        default=lambda s: s._default_parent(),
        domain=[("usage", "=", "view")],
    )
    zone_name = fields.Char(
        required=True,
        help="Human name, e.g. '1st Floor', 'Ground Floor', 'Outside Yard'.",
    )

    rack_count = fields.Integer(
        default=0,
        help="How many racks to generate inside this zone.",
    )
    rack_start_number = fields.Integer(
        default=1,
        help="Starting rack number. If you already have R01..R32 elsewhere, use 33 here.",
    )
    rack_prefix = fields.Char(
        default="R",
        help="Rack code prefix. R → R01, R02, …",
    )
    rack_shelf_count = fields.Integer(
        default=6,
        string="Shelves per rack",
        help="Number of horizontal shelves in each generated rack.",
    )
    rack_column_count = fields.Integer(
        default=3,
        string="Columns per rack",
        help="Number of vertical compartments per shelf in each generated rack.",
    )
    rack_slot_count = fields.Integer(
        default=1,
        string="Slots per compartment",
        help="Sub-divisions inside each compartment.",
    )
    rack_capacity_per_slot = fields.Float(default=0.0)

    floor_count = fields.Integer(
        default=0,
        help="How many open floor zones to generate inside this zone.",
    )
    floor_start_number = fields.Integer(default=1)
    floor_prefix = fields.Char(default="F")
    floor_capacity = fields.Float(default=0.0)

    @api.model
    def _default_parent(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        return wh and wh.lot_stock_id or False

    def action_generate(self):
        self.ensure_one()
        Loc = self.env["stock.location"]
        company_id = self.parent_location_id.company_id.id

        # 1. The zone view location itself.
        existing = Loc.search(
            [
                ("location_id", "=", self.parent_location_id.id),
                ("name", "=", self.zone_name),
            ],
            limit=1,
        )
        if existing:
            zone = existing
            if zone.wms_location_type != "zone":
                zone.write({"wms_location_type": "zone"})
        else:
            zone = Loc.create(
                {
                    "name": self.zone_name,
                    "location_id": self.parent_location_id.id,
                    "company_id": company_id,
                    "usage": "view",
                    "wms_location_type": "zone",
                }
            )

        # 2. Racks under the zone — delegate to the rack generator wizard
        #    in quick-grid mode (every rack same shelves×columns).
        created_racks = 0
        prefix = (self.rack_prefix or "R").strip().upper()
        for n in range(self.rack_start_number, self.rack_start_number + max(0, self.rack_count)):
            code = f"{prefix}{n:02d}"
            if Loc.search([("wms_rack_code", "=", code)], limit=1):
                continue
            gen = self.env["wms.rack.generator"].create(
                {
                    "warehouse_id": self.warehouse_id.id,
                    "parent_location_id": zone.id,
                    "rack_code": code,
                    "shelf_count": self.rack_shelf_count or 6,
                    "column_count": self.rack_column_count or 3,
                    "default_slot_count": self.rack_slot_count or 1,
                    "capacity_per_slot": self.rack_capacity_per_slot,
                }
            )
            gen.action_generate()
            created_racks += 1

        # 3. Floor zones under the zone.
        created_floors = 0
        if self.floor_count > 0:
            gen = self.env["wms.floor.zone.generator"].create(
                {
                    "warehouse_id": self.warehouse_id.id,
                    "parent_location_id": zone.id,
                    "zone_prefix": self.floor_prefix or "F",
                    "count": self.floor_count,
                    "start_number": self.floor_start_number,
                    "capacity_units": self.floor_capacity,
                }
            )
            gen.action_generate()
            created_floors = self.floor_count

        return {
            "type": "ir.actions.act_window",
            "name": f"Zone '{zone.name}'",
            "res_model": "stock.location",
            "res_id": zone.id,
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_zone_name": zone.name,
                "summary": (
                    f"Created zone with {created_racks} new rack(s) "
                    f"and {created_floors} floor zone(s)."
                ),
            },
        }

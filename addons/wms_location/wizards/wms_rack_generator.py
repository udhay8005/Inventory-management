from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.stock_location import MAX_LEVELS, MAX_SLOTS


class WmsRackGenerator(models.TransientModel):
    """Wizard that creates one Rack + 6 Levels + N Dividers per Level +
    3 Slots per Divider in a single click.

    Single point of creation guarantees the hierarchy constraints in
    stock_location.py are satisfied. Manual creation is still possible but
    fiddly — operators use this wizard.

    Total slots created: 6 * dividers_per_level * 3
      (e.g. dividers_per_level=4 → 72 slots; =3 → 54; =2 → 36)
    """

    _name = "wms.rack.generator"
    _description = "Generate a Rack with all levels, dividers and slots"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
    )
    parent_location_id = fields.Many2one(
        "stock.location",
        string="Parent location",
        required=True,
        help="Usually the warehouse's stock location, e.g. WH/Stock.",
        default=lambda self: self._default_parent_location(),
    )
    rack_code = fields.Char(
        required=True, default="R-01", help="Will become the rack's name suffix."
    )
    dividers_per_level = fields.Integer(
        required=True,
        default=4,
        help="How many dividers each of the 6 levels will have.",
    )
    capacity_per_slot = fields.Float(default=0.0, help="Optional soft cap per slot.")
    level_prefix = fields.Char(default="L", help="Prefix for level names (e.g. L → L-1).")
    divider_prefix = fields.Char(default="D")
    slot_prefix = fields.Char(default="S")

    @api.model
    def _default_parent_location(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        return wh and wh.lot_stock_id or False

    def action_generate(self):
        self.ensure_one()
        if self.dividers_per_level < 1:
            raise UserError("dividers_per_level must be at least 1.")

        Location = self.env["stock.location"]
        company_id = self.parent_location_id.company_id.id

        existing = Location.search(
            [
                ("location_id", "=", self.parent_location_id.id),
                ("wms_location_type", "=", "rack"),
                ("wms_rack_code", "=", self.rack_code),
            ],
            limit=1,
        )
        if existing:
            raise UserError(
                "A rack with code %s already exists under %s."
                % (self.rack_code, self.parent_location_id.display_name)
            )

        # 1. Rack (a view location; doesn't hold stock itself)
        rack = Location.create(
            {
                "name": self.rack_code,
                "location_id": self.parent_location_id.id,
                "company_id": company_id,
                "usage": "view",
                "wms_location_type": "rack",
                "wms_rack_code": self.rack_code,
                "barcode": self.rack_code,
            }
        )

        # 2. 6 Levels x N Dividers x 3 Slots
        for lvl in range(1, MAX_LEVELS + 1):
            level = Location.create(
                {
                    "name": "%s-%d" % (self.level_prefix, lvl),
                    "location_id": rack.id,
                    "company_id": company_id,
                    "usage": "view",
                    "wms_location_type": "level",
                    "wms_level_number": lvl,
                    "barcode": "%s-L%d" % (self.rack_code, lvl),
                }
            )
            for d in range(1, self.dividers_per_level + 1):
                divider = Location.create(
                    {
                        "name": "%s-%d" % (self.divider_prefix, d),
                        "location_id": level.id,
                        "company_id": company_id,
                        "usage": "view",
                        "wms_location_type": "divider",
                        "wms_divider_number": d,
                        "barcode": "%s-L%d-D%d" % (self.rack_code, lvl, d),
                    }
                )
                for s in range(1, MAX_SLOTS + 1):
                    Location.create(
                        {
                            "name": "%s-%d" % (self.slot_prefix, s),
                            "location_id": divider.id,
                            "company_id": company_id,
                            "usage": "internal",  # only slots actually hold stock
                            "wms_location_type": "slot",
                            "wms_slot_number": s,
                            "wms_capacity_units": self.capacity_per_slot,
                            "barcode": "%s-L%d-D%d-S%d" % (self.rack_code, lvl, d, s),
                        }
                    )

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.location",
            "res_id": rack.id,
            "view_mode": "form",
            "target": "current",
        }

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.stock_location import MAX_DIVIDERS, MAX_SLOTS


class WmsRackGenerator(models.TransientModel):
    """Wizard that creates one Rack location + its 6 dividers + 18 slots.

    Single point of creation guarantees the constraints in stock_location.py
    are satisfied. Manual creation through stock.location form still works
    but is fiddly — operators use this wizard.
    """
    _name = "wms.rack.generator"
    _description = "Generate a Rack with all dividers and slots"

    warehouse_id = fields.Many2one(
        "stock.warehouse", required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
    )
    parent_location_id = fields.Many2one(
        "stock.location",
        string="Parent location",
        required=True,
        help="Usually the warehouse's stock location, e.g. WH/Stock.",
        default=lambda self: self._default_parent_location(),
    )
    rack_code = fields.Char(required=True, default="R-01",
                            help="Will become the rack's name suffix.")
    capacity_per_slot = fields.Float(default=0.0, help="Optional soft cap per slot.")
    slot_prefix = fields.Char(default="S", help="Prefix for slot names (e.g. S → S-1).")
    divider_prefix = fields.Char(default="D", help="Prefix for divider names.")

    @api.model
    def _default_parent_location(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        return wh and wh.lot_stock_id or False

    def action_generate(self):
        self.ensure_one()
        Location = self.env["stock.location"]

        # 1. The rack
        existing = Location.search([
            ("location_id", "=", self.parent_location_id.id),
            ("wms_location_type", "=", "rack"),
            ("wms_rack_code", "=", self.rack_code),
        ], limit=1)
        if existing:
            raise UserError(
                "A rack with code %s already exists under %s."
                % (self.rack_code, self.parent_location_id.display_name)
            )

        rack = Location.create({
            "name": self.rack_code,
            "location_id": self.parent_location_id.id,
            "usage": "view",          # rack itself is not a stocking location
            "wms_location_type": "rack",
            "wms_rack_code": self.rack_code,
            "barcode": self.rack_code,
        })

        # 2. Six dividers + 3 slots each.
        for d in range(1, MAX_DIVIDERS + 1):
            divider = Location.create({
                "name": "%s-%d" % (self.divider_prefix, d),
                "location_id": rack.id,
                "usage": "view",
                "wms_location_type": "divider",
                "wms_divider_number": d,
                "barcode": "%s-D%d" % (self.rack_code, d),
            })
            for s in range(1, MAX_SLOTS + 1):
                Location.create({
                    "name": "%s-%d" % (self.slot_prefix, s),
                    "location_id": divider.id,
                    "usage": "internal",  # only slots actually hold stock
                    "wms_location_type": "slot",
                    "wms_slot_number": s,
                    "wms_capacity_units": self.capacity_per_slot,
                    "barcode": "%s-D%d-S%d" % (self.rack_code, d, s),
                })

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.location",
            "res_id": rack.id,
            "view_mode": "form",
            "target": "current",
        }

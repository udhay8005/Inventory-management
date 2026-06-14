from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsFloorZoneGenerator(models.TransientModel):
    """Create one or more 'floor' stocking locations — open areas with
    no rack/level/divider hierarchy.

    Use cases:
      - Pallet area inside / outside the warehouse
      - Single-shelf slab not worth modelling as 6×N×3
      - Outside yard bay
      - Receiving / staging dock
      - Damaged-goods bench

    Each floor location:
      - usage='internal' (so stock.quant can land directly)
      - gets a unique scannable barcode
      - lives under a parent view location of the operator's choice
    """

    _name = "wms.floor.zone.generator"
    _description = "Generate floor / open-area stocking locations"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
    )
    parent_location_id = fields.Many2one(
        "stock.location",
        string="Parent area",
        required=True,
        help="Where to place these floor zones. Usually the main warehouse "
        "stock location, or a building / floor zone underneath it.",
        default=lambda self: self._default_parent_location(),
        domain=[("usage", "=", "view")],
    )
    zone_prefix = fields.Char(
        required=True,
        default="F",
        help="Prefix for zone names + barcodes, e.g. 'F' for floor → F-01, F-02 ...",
    )
    count = fields.Integer(
        required=True,
        default=1,
        help="How many floor zones to create.",
    )
    start_number = fields.Integer(
        required=True,
        default=1,
        help="Starting sequence number. Useful if you've already used F-01..F-05.",
    )
    capacity_units = fields.Float(
        default=0.0,
        help="Optional soft capacity per zone (number of units it can hold).",
    )

    @api.model
    def _default_parent_location(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        return wh and wh.lot_stock_id or False

    def action_generate(self):
        self.ensure_one()
        if self.count < 1:
            raise UserError("Count must be at least 1.")

        Location = self.env["stock.location"]
        company_id = self.parent_location_id.company_id.id
        prefix = (self.zone_prefix or "F").strip().upper()
        created = []

        for n in range(self.start_number, self.start_number + self.count):
            code = f"{prefix}-{n:02d}"

            existing = Location.search(
                [
                    ("location_id", "=", self.parent_location_id.id),
                    ("name", "=", code),
                ],
                limit=1,
            )
            if existing:
                continue  # idempotent re-runs

            # Build a unique barcode under the parent. The first-4-alnum prefix
            # of the parent name is human-friendly but NOT unique: two parents
            # like "Pharmacy Building" / "Pharma Store" both compress to "PHAR"
            # and would mint the same barcode, hitting stock.location's global
            # barcode-unique constraint and rolling back the whole batch with a
            # cryptic error. So if the friendly barcode already belongs to
            # another location, fall back to one keyed on the parent id (always
            # unique); if even that clashes, fail with a clear message.
            parent_prefix = "".join(c for c in self.parent_location_id.name if c.isalnum())[
                :4
            ].upper()
            barcode = f"{parent_prefix}-{code}" if parent_prefix else code
            clash = Location.search([("barcode", "=", barcode)], limit=1)
            if clash and clash.location_id.id != self.parent_location_id.id:
                pid = self.parent_location_id.id
                barcode = f"{parent_prefix}{pid}-{code}" if parent_prefix else f"{pid}-{code}"
                clash2 = Location.search([("barcode", "=", barcode)], limit=1)
                if clash2:
                    raise UserError(
                        "Cannot generate floor zone %s: the barcode %s already "
                        "belongs to %s. Rename the parent location or choose a "
                        "different zone prefix, then try again."
                        % (code, barcode, clash2.complete_name or clash2.display_name)
                    )

            loc = Location.create(
                {
                    "name": code,
                    "location_id": self.parent_location_id.id,
                    "company_id": company_id,
                    "usage": "internal",
                    "wms_location_type": "floor",
                    "wms_capacity_units": self.capacity_units,
                    "barcode": barcode,
                }
            )
            created.append(loc)

        if not created:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "title": "Nothing to do",
                    "message": "Every requested zone already exists.",
                    "sticky": False,
                },
            }

        # Open the list so the operator can immediately print labels.
        return {
            "type": "ir.actions.act_window",
            "name": "Generated floor zones",
            "res_model": "stock.location",
            "view_mode": "list,form",
            "domain": [("id", "in", [loc.id for loc in created])],
            "target": "current",
        }

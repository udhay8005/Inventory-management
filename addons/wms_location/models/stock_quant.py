from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Climb the parent chain once and store the IDs so dashboards don't
    # recompute it on every read. After the rack model redesign the
    # hierarchy is: Rack → Compartment → Slot (shelves are coordinates
    # on the Compartment, not a separate stock.location).
    wms_slot_id = fields.Many2one(
        "stock.location",
        compute="_compute_wms_hierarchy",
        store=True,
        index=True,
    )
    wms_compartment_id = fields.Many2one(
        "stock.location",
        compute="_compute_wms_hierarchy",
        store=True,
        index=True,
    )
    wms_rack_id = fields.Many2one(
        "stock.location",
        compute="_compute_wms_hierarchy",
        store=True,
        index=True,
    )

    @api.depends(
        "location_id",
        "location_id.wms_location_type",
        "location_id.location_id",
        "location_id.location_id.location_id",
    )
    def _compute_wms_hierarchy(self):
        for q in self:
            slot = compartment = rack = False
            cur = q.location_id
            # Walk up at most 3 levels (slot → compartment → rack).
            for _ in range(4):
                if not cur:
                    break
                t = cur.wms_location_type
                if t == "slot" and not slot:
                    slot = cur
                elif t == "compartment" and not compartment:
                    compartment = cur
                elif t == "rack" and not rack:
                    rack = cur
                cur = cur.location_id
            q.wms_slot_id = slot
            q.wms_compartment_id = compartment
            q.wms_rack_id = rack

from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Convenience: hop up the parent chain so dashboards don't recompute it.
    wms_slot_id = fields.Many2one(
        "stock.location",
        compute="_compute_wms_hierarchy",
        store=True,
        index=True,
    )
    wms_divider_id = fields.Many2one(
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

    @api.depends("location_id", "location_id.wms_location_type",
                 "location_id.location_id", "location_id.location_id.location_id")
    def _compute_wms_hierarchy(self):
        for q in self:
            loc = q.location_id
            slot = divider = rack = False
            if loc and loc.wms_location_type == "slot":
                slot = loc
                divider = loc.location_id if loc.location_id.wms_location_type == "divider" else False
                if divider:
                    rack = divider.location_id if divider.location_id.wms_location_type == "rack" else False
            elif loc and loc.wms_location_type == "divider":
                divider = loc
                rack = loc.location_id if loc.location_id.wms_location_type == "rack" else False
            elif loc and loc.wms_location_type == "rack":
                rack = loc
            q.wms_slot_id = slot
            q.wms_divider_id = divider
            q.wms_rack_id = rack

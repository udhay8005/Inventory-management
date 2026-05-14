from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Climb the parent chain once and store the IDs so dashboards don't
    # recompute it on every read.
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
    wms_level_id = fields.Many2one(
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
        "location_id.location_id.location_id.location_id",
    )
    def _compute_wms_hierarchy(self):
        for q in self:
            slot = divider = level = rack = False
            loc = q.location_id
            # Walk up at most 4 levels.
            chain = []
            cur = loc
            for _ in range(5):
                if not cur:
                    break
                chain.append(cur)
                cur = cur.location_id
            for node in chain:
                t = node.wms_location_type
                if t == "slot" and not slot:
                    slot = node
                elif t == "divider" and not divider:
                    divider = node
                elif t == "level" and not level:
                    level = node
                elif t == "rack" and not rack:
                    rack = node
            q.wms_slot_id = slot
            q.wms_divider_id = divider
            q.wms_level_id = level
            q.wms_rack_id = rack

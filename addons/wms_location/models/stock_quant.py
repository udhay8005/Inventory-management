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

    def _wms_sorted_for_removal(self):
        """Single authoritative WMS removal ordering (Critical #5).

        Shared by the Scan Issue planner (find_oldest_quants_for_product) and
        the _gather reservation hook so every removal path agrees. Pooling is
        always within one product/template (no cross-product substitution);
        order oldest-first by in_date (FIFO), id as a stable tiebreaker.
        """
        return self.sorted(key=lambda q: (q.in_date or q.create_date, q.id))

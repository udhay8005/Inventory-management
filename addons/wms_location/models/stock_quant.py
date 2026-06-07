from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Truthy spellings accepted for the opt-in capacity System Parameter.
_ENFORCE_TRUE = ("1", "true", "True", "yes", "on")


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

    @api.constrains("quantity", "location_id", "product_id")
    def _wms_check_location_capacity(self):
        """Opt-in slot capacity guard (Batch 4).

        Off by default (zero behaviour change). When an Admin sets the System
        Parameter ``wms_location.enforce_capacity`` to ``1``, a write that
        pushes an internal location's physical on-hand over its
        ``wms_capacity_units`` is refused and rolled back — nothing is forced.

        Cheap when disabled: one cached parameter read, then return. When on,
        only the locations actually touched that carry a positive capacity are
        summed, so the cost scales with the move, not the warehouse.
        """
        param = (
            self.env["ir.config_parameter"].sudo().get_param("wms_location.enforce_capacity", "0")
        )
        if param not in _ENFORCE_TRUE:
            return
        Quant = self.env["stock.quant"].sudo()
        capped = self.location_id.filtered(
            lambda loc: loc.usage == "internal" and loc.wms_capacity_units > 0
        )
        for loc in capped:
            on_hand = sum(
                Quant.search([("location_id", "=", loc.id), ("quantity", ">", 0)]).mapped(
                    "quantity"
                )
            )
            if on_hand > loc.wms_capacity_units:
                raise ValidationError(
                    "Location %s is over capacity.\n"
                    "It would hold %g units, but its capacity is %g.\n"
                    "Put the extra stock in another slot, or raise this "
                    "location's capacity.\n\n"
                    "(Capacity enforcement is switched on. An Admin can turn it "
                    "off under Settings -> Technical -> System Parameters by "
                    "setting wms_location.enforce_capacity back to 0.)"
                    % (loc.display_name, on_hand, loc.wms_capacity_units)
                )

    def _wms_sorted_for_removal(self):
        """Single authoritative WMS removal ordering (Critical #5).

        Shared by the Scan Issue planner (find_oldest_quants_for_product) and
        the _gather reservation hook so every removal path agrees. Pooling is
        always within one product/template (no cross-product substitution).

        Order:
          * If the template carries a wms_expiry_date OR its
            wms_product_kind is in EXPIRY_SENSITIVE_KINDS (medicine, feed,
            fluid, pooja), sort EARLIEST-EXPIRING FIRST (FEFO), falling back
            to in_date when expiry is not set on a sibling quant.
          * Otherwise sort OLDEST-ARRIVING FIRST (FIFO).

        FPAT High: the wizard previously banner-printed "FEFO: earliest expiry
        first" for medicine/feed/fluid/pooja but the actual sort never read
        wms_expiry_date. A January-arrived batch with December expiry shipped
        ahead of a March-arrived batch expiring next month, and the
        expiring batch ended up thrown out. This makes the promise honest.
        """
        from datetime import date

        from .product_template import EXPIRY_SENSITIVE_KINDS

        far_future = date(9999, 12, 31)
        # All quants in `self` share a template (the planner pools by template
        # already) so we read the kind+expiry off the first one for the policy
        # decision, then sort the whole recordset by per-quant expiry.
        if not self:
            return self
        tmpl = self[0].product_id.product_tmpl_id
        use_fefo = tmpl.wms_product_kind in EXPIRY_SENSITIVE_KINDS or bool(tmpl.wms_expiry_date)
        if use_fefo:
            return self.sorted(
                key=lambda q: (
                    q.product_id.product_tmpl_id.wms_expiry_date or far_future,
                    q.in_date or q.create_date,
                    q.id,
                )
            )
        return self.sorted(key=lambda q: (q.in_date or q.create_date, q.id))

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
        # FPAT High: serialise the on-hand recompute under concurrent writers
        # to the same capped location. Without this lock two parallel quant
        # writes can each see on_hand <= capacity, each pass the check, and
        # together end up over capacity. Locking the touched location rows
        # first forces the second writer to wait until the first commits, so
        # its recompute sees the updated total.
        if capped:
            self.env.cr.execute(
                "SELECT id FROM stock_location WHERE id = ANY(%s) FOR UPDATE",
                (list(capped.ids),),
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

        Ordering primitive:
          * EXPIRY_SENSITIVE_KINDS (medicine / feed / fluid / pooja), or any
            template carrying a wms_expiry_date -> EARLIEST-EXPIRING FIRST
            (FEFO), tie-broken by in_date then id;
          * otherwise OLDEST-ARRIVING FIRST (FIFO).

        Effective behaviour in the Scan Issue path: the planner pools within
        ONE template, and wms_expiry_date is a *template* field, so every
        candidate quant in that call shares the same expiry and the FEFO key
        collapses to plain FIFO (oldest arrival first). That is why the Scan
        Issue feedback says "oldest stock first", not "earliest expiry first" -
        a single issue is one product, so there is no batch to expiry-sort
        against. Perishable-rotation risk is surfaced by the Expiry-Alert
        report instead. The expiry sort below stays correct for any caller that
        pools ACROSS templates (covered by test_fpat_fx2 / test_removal_engine);
        true per-BATCH FEFO would require stock.lot expiry, which the trust does
        not run today.
        """
        from datetime import date

        from .product_template import EXPIRY_SENSITIVE_KINDS

        far_future = date(9999, 12, 31)
        # All quants in `self` share a template in the planner path (pooled by
        # template) so the policy decision off the first one is representative.
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

    # ---- Negative-slot guard (UAT R3) -----------------------------------
    # A manual Internal Transfer happily validated 10 units out of a slot
    # holding 4, leaving the slot at -6 "on hand" — silent phantom-negative
    # stock (seen live: a slot at -2 after a walkthrough transfer). Scan
    # flows reserve properly and can't do this; the raw transfer screen can.
    # Physical shelves can't hold negative stock, so refuse the write.
    #
    # Scoped tightly to WMS storage leaves (slot / floor, internal): staging
    # locations (trust-use, Damage, Repair, Inventory adjustment, Vendors)
    # keep Odoo's native permissive behaviour, and data-repair scripts can
    # bypass with context wms_allow_negative=True.
    @api.constrains("quantity")
    def _check_wms_slot_not_negative(self):
        if self.env.context.get("wms_allow_negative"):
            return
        for quant in self:
            loc = quant.location_id
            if (
                quant.quantity < -1e-5
                and loc.usage == "internal"
                and loc.wms_location_type in ("slot", "floor")
            ):
                raise ValidationError(
                    "This would leave %(loc)s at %(qty)g × %(product)s — a "
                    "physical shelf can't hold negative stock. The slot only "
                    "has what it has: lower the quantity, pick from the slot "
                    "that actually holds the stock, or correct the count "
                    "first with an Inventory audit."
                    % {
                        "loc": loc.display_name,
                        "qty": quant.quantity,
                        "product": quant.product_id.display_name,
                    }
                )

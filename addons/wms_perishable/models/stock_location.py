"""V20-011 — keep expired stock out of the Scan Issue plan.

The frozen v19 planner (stock.location.find_oldest_quants_for_product) searches
quants directly and does NOT apply product_expiry's `with_expiration` gather
domain — so it would PLAN against an expired lot, which then fails to RESERVE
at validate (product_expiry blocks it), surfacing a confusing late error. We
exclude expired stock up front, on the SAME criterion the reservation uses:
stock.quant.removal_date (= lot.removal_date = expiration_date - removal_time)
in the past. So the plan is honest and the shortfall reflects only stock that
can actually be issued.

Why re-implement instead of post-filtering super()'s plan: super() greedily
allocates the earliest-expiring lots FIRST (FEFO) and stops at remaining<=0, so
a post-filter would drop expired lots it already counted on and lose the valid
lots it skipped — under-allocating. We must exclude before the greedy walk.

Scope guards (zero risk to v19 behaviour):
  * non-perishable products (no use_expiration_date) -> delegate to v19 super();
  * `wms_allow_expired_removal` context (manager override V20-011b, disposal
    V20-011c) -> delegate to v19 super() so expired stock stays reachable.
The exclusion lives HERE, in the issue planner — never in
stock.quant._wms_sorted_for_removal (that sort is shared with _gather and the
disposal flows and must stay a pure ordering function).
"""

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def find_oldest_quants_for_product(self, product_id, qty_needed, parent_location_id=None):
        scanned = self.env["product.product"].browse(product_id).exists()
        if (
            self.env.context.get("wms_allow_expired_removal")
            or not scanned
            or scanned.tracking != "lot"
        ):
            # Non-lot product, unknown product, or an explicit override/disposal
            # path: plan exactly as v19 does (expired/blocked stock stays reachable).
            return super().find_oldest_quants_for_product(
                product_id, qty_needed, parent_location_id=parent_location_id
            )

        # Lot-tracked issue: same candidate set + ordering as v19, but excluding
        # stock that cannot actually be issued:
        #   * EXPIRED — removal_date in the past (V20-011), mirroring the
        #     reservation gather domain so the plan matches what validate can do;
        #   * NON-AVAILABLE lots — recalled / quarantined / destroyed
        #     (V20-013/014); only a lot in state 'available' may be issued.
        # No-lot quants (removal_date / lot_id NULL) are kept, so non-expiry
        # lot-tracked stock behaves exactly as v19 until a lot is flagged.
        product_ids = scanned.product_tmpl_id.product_variant_ids.ids
        now = fields.Datetime.now()
        base_domain = [
            ("product_id", "in", product_ids),
            ("quantity", ">", 0),
            ("location_id.usage", "=", "internal"),
            ("location_id.wms_is_damage", "=", False),
            ("location_id.wms_is_repair", "=", False),
            "|",
            ("removal_date", "=", False),
            ("removal_date", ">=", now),
            "|",
            ("lot_id", "=", False),
            ("lot_id.wms_lot_state", "=", "available"),
        ]
        strict = list(base_domain)
        if parent_location_id:
            strict.append(("location_id.id", "child_of", parent_location_id))
        quants = self.env["stock.quant"].search(strict)
        if not quants and parent_location_id:
            company_id = self.env.company.id
            fallback = list(base_domain) + [
                "|",
                ("company_id", "=", company_id),
                ("company_id", "=", False),
            ]
            quants = self.env["stock.quant"].search(fallback)

        quants = quants._wms_sorted_for_removal()
        plan = []
        remaining = qty_needed
        for q in quants:
            if remaining <= 0:
                break
            available = q.quantity - q.reserved_quantity
            if available <= 0:
                continue
            take = min(available, remaining)
            plan.append((q, take))
            remaining -= take
        return plan, remaining

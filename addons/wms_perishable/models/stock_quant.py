"""V20-008 — stored, indexed stock.quant.wms_effective_expiry.

The single per-quant value the FEFO removal sort reads (V20-009): the lot's own
expiration_date when lot-tracked, else the product template's wms_expiry_date.
Stored + indexed because the v19 sort keyed on a *template* field and a per-lot
lambda traversal at sort time would be an N+1 on large quant tables (build
condition #1, docs/v20-perishable-engine/09-phase0-verification.md). FEFO itself
(the sort override) lands in V20-009; this ticket only lands the field + index.
"""

from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    wms_effective_expiry = fields.Date(
        string="Effective expiry",
        compute="_compute_wms_effective_expiry",
        store=True,
        index=True,
        help="The lot's expiry if lot-tracked, otherwise the product template "
        "fallback (wms_expiry_date). The single value the FEFO removal sort reads.",
    )

    @api.depends(
        "lot_id",
        "lot_id.expiration_date",
        "product_id.product_tmpl_id.wms_expiry_date",
    )
    def _compute_wms_effective_expiry(self):
        for q in self:
            # lot.expiration_date (product_expiry) is a Datetime; FEFO is
            # day-granular, so coerce to a date. No lot expiry -> template
            # fallback. Neither -> leave NULL (the sort applies a far-future
            # sentinel in Python; a literal 9999 here would pollute report
            # ordering that keys on this column).
            lot_exp = q.lot_id.expiration_date if q.lot_id else False
            if lot_exp:
                q.wms_effective_expiry = lot_exp.date()
            else:
                q.wms_effective_expiry = q.product_id.product_tmpl_id.wms_expiry_date or False

    def _get_gather_domain(
        self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False
    ):
        # V20-011c disposal carve-out. product_expiry adds a hard removal_date
        # exclusion to the gather domain whenever `with_expiration` is in the
        # context (set per-move for use_expiration_date products), so expired
        # stock can't be reserved for ANYTHING — including a manual Damage/scrap
        # to clear it off the shelf. When a disposal/override flow sets
        # `wms_allow_expired_removal`, we neutralise `with_expiration` for this
        # one domain build so expired stock becomes reservable for disposal.
        # Surgical: every reservation WITHOUT that flag is byte-for-byte v19.
        records = self
        if self.env.context.get("wms_allow_expired_removal"):
            records = self.with_context(with_expiration=False)
        return super(StockQuant, records)._get_gather_domain(
            product_id,
            location_id,
            lot_id=lot_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )

    def _wms_sorted_for_removal(self):
        """V20-009 — FEFO now reads the per-quant STORED wms_effective_expiry
        (lot expiry, else template fallback) instead of the v19 template-only
        field, so multiple lots of one product sort earliest-expiry-first.

        Everything else is the v19 contract verbatim: the FIFO-vs-FEFO kind
        gate is unchanged (so non-perishables — even if lot-tracked — stay
        strict FIFO), and this is PURE ordering with NO filtering. Expired-lot
        exclusion is owned by Odoo product_expiry's gather domain; lot-state
        (quarantine/recall) exclusion is owned by V20-013/014. Overriding this
        single chokepoint reaches both the Scan Issue planner and the _gather
        reservation path (wms_fifo._gather calls it), and the auto-split across
        lots is then native: a move carrying no lot_id has Odoo walk this
        FEFO-ordered recordset, splitting into one move line per lot.
        """
        from datetime import date

        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        if not self:
            return self
        far_future = date(9999, 12, 31)
        # All quants in a planner call share one template, so the policy off the
        # first is representative (v19 contract). Reading the per-quant stored
        # field also makes any cross-template _gather ordering correct.
        tmpl = self[0].product_id.product_tmpl_id
        use_fefo = tmpl.wms_product_kind in EXPIRY_SENSITIVE_KINDS or bool(tmpl.wms_expiry_date)
        if use_fefo:
            return self.sorted(
                key=lambda q: (
                    q.wms_effective_expiry or far_future,
                    q.in_date or q.create_date,
                    q.id,
                )
            )
        return self.sorted(key=lambda q: (q.in_date or q.create_date, q.id))

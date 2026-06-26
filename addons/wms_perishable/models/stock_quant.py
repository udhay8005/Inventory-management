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

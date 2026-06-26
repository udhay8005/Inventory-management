"""V20-010 — richer Scan Issue plan preview for perishables.

The planner already orders FEFO (V20-009). This adds per-lot visibility to the
plan: which batch each line draws from, that batch's OWN effective expiry (not
the template's), and the balance left in the lot after the take — plus
FEFO-aware success feedback. Additive _inherit over the frozen v19 wizard: the
v19 plan + feedback are produced by super() and enriched here.

The shortfall WHY-breakdown (excluded expired / quarantined / recalled)
co-delivers with the planner exclusion logic in V20-011/013/014 — there is
nothing to break down until the planner actually excludes those lots.
"""

from odoo import api, fields, models


class WmsScanIssuePlan(models.TransientModel):
    _inherit = "wms.scan.issue.plan"

    lot_id = fields.Many2one(
        "stock.lot",
        string="Batch",
        help="The specific batch this line draws from (FEFO — earliest expiry first).",
    )
    resulting_balance = fields.Float(
        string="Left after",
        compute="_compute_resulting_balance",
        help="Units remaining in this batch/slot after the planned take.",
    )

    @api.depends("available", "take")
    def _compute_resulting_balance(self):
        for line in self:
            line.resulting_balance = (line.available or 0.0) - (line.take or 0.0)


class WmsScanIssue(models.TransientModel):
    _inherit = "wms.scan.issue"

    def action_plan(self):
        res = super().action_plan()
        # V20-010: enrich each FEFO-ordered plan line with its batch + the
        # batch's own effective expiry (the v19 line carried the *template*
        # expiry, which is lot-blind once stock is tracked per lot).
        for line in self.plan_line_ids:
            quant = line.quant_id
            if quant.lot_id:
                line.lot_id = quant.lot_id.id
            if quant.wms_effective_expiry:
                line.expiry_date = quant.wms_effective_expiry
        # For a perishable, reword the success feedback: removal is
        # earliest-expiry-first (FEFO, not plain FIFO) and show the resulting
        # on-hand balance so the operator previews the after-state.
        if self.plan_line_ids and not self.short_qty:
            product = self.plan_line_ids[0].product_id
            if self._wms_issue_is_perishable(product):
                planned = sum(self.plan_line_ids.mapped("take"))
                on_hand = self._wms_product_on_hand(product)
                self.feedback = (
                    "Planned %g × %s across %d lot(s) — earliest expiry first. "
                    "On hand %g → %g after this issue."
                ) % (
                    planned,
                    product.display_name,
                    len(self.plan_line_ids),
                    on_hand,
                    on_hand - planned,
                )
        return res

    @api.model
    def _wms_issue_is_perishable(self, product):
        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        tmpl = product.product_tmpl_id
        return tmpl.wms_product_kind in EXPIRY_SENSITIVE_KINDS or bool(tmpl.wms_expiry_date)

    def _wms_product_on_hand(self, product):
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", self.warehouse_id.lot_stock_id.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        return sum(quants.mapped("quantity"))

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
from odoo.exceptions import UserError


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

    wms_has_expired_shortfall = fields.Boolean(
        readonly=True,
        help="Set when the plan fell short and expired stock is on hand — a "
        "Manager can override the expiry block to issue it.",
    )
    wms_has_short_dated_issue = fields.Boolean(
        readonly=True,
        help="V20-022 — set when the FEFO plan draws near-expiry stock with less "
        "than the product's minimum issue shelf life left (but not yet expired). "
        "A Manager can approve issuing it.",
    )

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
        # V20-011: shortfall breakdown — when the order can't be filled, say how
        # much physically-present stock is EXPIRED (excluded from the plan, since
        # the planner now drops it), so the operator isn't told "stock out" while
        # expired stock sits on the shelf, and knows a Manager can override.
        self.wms_has_expired_shortfall = False
        if self.short_qty:
            product = self._wms_resolve_scanned_product()
            expired_qty = self._wms_expired_on_hand(product) if product else 0.0
            if expired_qty:
                self.wms_has_expired_shortfall = True
                self.feedback = (self.feedback or "") + (
                    " ⚠ %g unit(s) of %s on hand are EXPIRED and cannot be issued "
                    "(a Manager can override)." % (expired_qty, product.display_name)
                )
        # V20-022 — flag when the FEFO plan draws near-expiry stock below the
        # product's min-issue shelf life so the manager-approval button shows.
        self.wms_has_short_dated_issue = bool(self._wms_short_dated_issue_lines())
        if self.wms_has_short_dated_issue and not self.short_qty:
            self.feedback = (self.feedback or "") + (
                " ⚠ Some planned stock is short-dated (below the min issue shelf "
                "life) — a Manager must approve issuing it."
            )
        return res

    def action_validate(self):
        # V20-022 — short-dated-at-issue guard (warn + manager approval, spec
        # §2.8/3.7). Skipped when a Manager has approved short-dated issue, or
        # during the expired override (a Manager already owns that decision).
        if not (
            self.env.context.get("wms_allow_short_dated_issue")
            or self.env.context.get("wms_expired_override")
        ):
            short = self._wms_short_dated_issue_lines()
            if short:
                raise UserError(self._wms_short_dated_issue_message(short))
        res = super().action_validate()
        # V20-019 — fire the 'issued' lifecycle hook for the lots actually
        # issued (only when a picking was created, i.e. not the approval path).
        if self.picking_id:
            lots = self.picking_id.move_line_ids.lot_id
            if lots:
                lots._wms_lifecycle_hook("issued", self.picking_id)
        return res

    # ---- V20-022: short-dated-at-issue guard --------------------------------
    def _wms_short_dated_issue_lines(self):
        """Planned plan lines whose drawn lot has LESS than the product's
        min-issue shelf life remaining, but is NOT already expired (expired is
        blocked separately by the planner exclusion). Returns a recordset of
        wms.scan.issue.plan lines."""
        out = self.plan_line_ids.browse()
        today = fields.Date.today()
        for line in self.plan_line_ids:
            if not line.lot_id:
                continue
            min_issue = line.product_id.product_tmpl_id._wms_resolve_shelf_life()["min_issue"]
            if min_issue <= 0:
                continue
            exp = line.expiry_date or (
                line.quant_id.wms_effective_expiry if line.quant_id else False
            )
            if not exp:
                continue
            days_left = (exp - today).days
            if 0 <= days_left < min_issue:
                out |= line
        return out

    def _wms_short_dated_issue_message(self, lines):
        today = fields.Date.today()
        rows = []
        for line in lines:
            exp = line.expiry_date
            left = (exp - today).days if exp else 0
            need = line.product_id.product_tmpl_id._wms_resolve_shelf_life()["min_issue"]
            rows.append(
                "- %s / %s: %d day(s) left (needs >= %d)"
                % (line.product_id.display_name, line.lot_id.name or "?", left, need)
            )
        return (
            "Short-dated at issue. The earliest-expiry stock for these line(s) has "
            "less remaining shelf life than the minimum for issuing:\n%s\n\nA "
            "Manager must approve issuing short-dated stock." % "\n".join(rows)
        )

    def action_override_short_dated_issue(self):
        """Manager-only: approve issuing short-dated (near-expiry) stock."""
        self.ensure_one()
        if not self._wms_is_manager():
            raise UserError(
                "Only a Manager can approve issuing short-dated stock. The guard "
                "keeps near-expiry stock from leaving without sign-off."
            )
        marker = "[SHORT-DATED ISSUE approved by %s]" % self.env.user.name
        note = (self.usage_note or "").strip()
        self.usage_note = (note + "\n" + marker) if note else marker
        return self.with_context(wms_allow_short_dated_issue=True).action_validate()

    @api.model
    def _wms_issue_is_perishable(self, product):
        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        tmpl = product.product_tmpl_id
        return tmpl.wms_product_kind in EXPIRY_SENSITIVE_KINDS or bool(tmpl.wms_expiry_date)

    def _wms_resolve_scanned_product(self):
        if not self.last_scan:
            return self.env["product.product"]
        info = self.env["wms.barcode.alias"].resolve(self.last_scan)
        return info.get("product") or self.env["product.product"]

    def _wms_expired_on_hand(self, product):
        """Physically-present-but-expired units (removal_date in the past) for
        the scanned product — the stock the planner now excludes from issue."""
        now = fields.Datetime.now()
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "in", product.product_tmpl_id.product_variant_ids.ids),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
                ("location_id.wms_is_damage", "=", False),
                ("location_id.wms_is_repair", "=", False),
                ("removal_date", "!=", False),
                ("removal_date", "<", now),
            ]
        )
        return sum(q.quantity - q.reserved_quantity for q in quants)

    def _wms_product_on_hand(self, product):
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("location_id", "child_of", self.warehouse_id.lot_stock_id.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        return sum(quants.mapped("quantity"))

    # ---- V20-011b: Manager override to ISSUE expired stock ------------------
    def _wms_is_manager(self):
        return self.env.user.has_group("wms_location.group_wms_manager")

    def _check_high_value(self):
        # A Manager performing the expired-override is already the approving
        # authority, so do NOT also route the issue through the keeper->manager
        # approval gate — its approval replay would not carry the carve-out
        # context and so could not reserve the expired stock. Outside the
        # override (or for a non-manager) the v19 gate is unchanged.
        if self.env.context.get("wms_expired_override") and self._wms_is_manager():
            return False
        return super()._check_high_value()

    def _check_min_life(self):
        if self.env.context.get("wms_expired_override") and self._wms_is_manager():
            return (False, self.env["product.product"], False)
        return super()._check_min_life()

    def action_override_expired_issue(self):
        """Manager-only: bypass the expiry block and issue expired stock.

        Re-plans INCLUDING expired lots (the planner delegates to v19 when the
        carve-out flag is set), then validates inline with the carve-out so the
        picking reserves the expired lots. Manager-gated in-method (the button
        is also group-restricted) and the authorising manager is stamped onto
        the usage note for the audit trail.
        """
        self.ensure_one()
        if not self._wms_is_manager():
            raise UserError(
                "Only a Manager can override the expiry block and issue expired "
                "stock. The block keeps expired medicine off the floor — a "
                "Manager must take responsibility to override it."
            )
        marker = "[EXPIRED-STOCK OVERRIDE authorised by %s]" % self.env.user.name
        note = (self.usage_note or "").strip()
        self.usage_note = (note + "\n" + marker) if note else marker
        wiz = self.with_context(
            wms_allow_expired_removal=True,
            wms_expired_override=True,
            wms_allow_short_dated_issue=True,
        )
        wiz.action_plan()
        return wiz.action_validate()

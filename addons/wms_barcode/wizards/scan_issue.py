from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.stock_picking import WMS_ISSUED_FOR_SELECTION


class WmsScanIssue(models.TransientModel):
    """Scan-based outbound issue with strict FIFO across slots.

    Operator scans a product barcode + qty. The wizard plans deductions
    against the oldest quants (via stock.location.find_oldest_quants_for_product)
    and shows them BEFORE validating, so a physical mis-count can be overridden
    before the picking commits.

    Inherits `barcodes.barcode_events_mixin` so any wireless/USB HID scanner
    fires `on_barcode_scanned` automatically.
    """

    _name = "wms.scan.issue"
    _description = "Scan-based issue (FIFO)"
    _inherit = ["barcodes.barcode_events_mixin"]

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        default=lambda s: s.env["stock.warehouse"].search([], limit=1),
    )
    destination_id = fields.Many2one(
        "stock.location",
        required=True,
        domain=[("usage", "in", ("customer", "production", "internal"))],
        default=lambda s: s._default_destination_id(),
        help="Where the issued stock goes. Defaults to the trust's "
        "'Trust internal use' location since the trust uses inventory "
        "internally rather than selling it. Admin can pick any other "
        "internal location (Cow Shed, Pooja Room, etc.) on the day "
        "without changing the default.",
    )

    @api.model
    def _default_destination_id(self):
        """The Trust uses stock internally rather than selling it.

        Prefer the seeded ``wms_location.stock_location_trust_use``;
        fall back to ``stock.stock_location_customers`` only if the
        WMS data file hasn't loaded yet (e.g. mid-install).
        """
        trust = self.env.ref("wms_location.stock_location_trust_use", raise_if_not_found=False)
        if trust:
            return trust
        return self.env.ref("stock.stock_location_customers", raise_if_not_found=False)

    last_scan = fields.Char()
    requested_qty = fields.Float(default=1.0)
    feedback = fields.Char(readonly=True)

    plan_line_ids = fields.One2many("wms.scan.issue.plan", "wizard_id")
    short_qty = fields.Float(readonly=True, help="Shortfall — what we couldn't allocate.")
    picking_id = fields.Many2one(
        "stock.picking",
        readonly=True,
        copy=False,
        help="The delivery this issue created. Set once validated so a "
        "double-click or a page refresh re-submitting the form cannot "
        "issue the same stock twice — the second attempt just re-opens "
        "the delivery that was already made.",
    )

    # ---- Audit trail -----------------------------------------------------
    # Captured at validate-time and copied onto the resulting picking, so
    # every issue records WHO took the stock, WHO authorised it, and which
    # keeper was running the store at that moment.
    taken_by = fields.Char(
        string="Taken by",
        required=True,
        help="Name of the person who is physically taking these items "
        "(e.g. the worker, department lead, or visitor).",
    )
    ordered_by = fields.Char(
        string="Ordered by",
        required=True,
        help="Name of the person who authorised this issue "
        "(the Manager / cow-care lead / project owner).",
    )
    storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        required=True,
        domain=[("active", "=", True)],
        help="The actual human running the desk right now. Pick from the "
        "roster the Admin maintains under Configuration → Store Keepers. "
        "If the name you want isn't here, ask the Admin to add it before "
        "validating.",
    )

    # Mandatory free-text reason for taking the stock. The taken_by /
    # ordered_by fields capture WHO; this captures WHY. The trust uses
    # it to reconcile against monthly cow-care plans and to spot
    # patterns (one team consistently over-pulling soap, for example).
    # Required = True so an issue can never go through without
    # accountability text.
    usage_note = fields.Text(
        string="Reason / usage note",
        required=True,
        help="Why is this stock being taken? Examples: 'morning feed for "
        "shed B', 'replacing broken pump in plumbing room', 'monthly "
        "vaccination round for calves'. Required — no issue without "
        "an explanation. Copied to the resulting picking's audit log.",
    )
    issued_for = fields.Selection(
        WMS_ISSUED_FOR_SELECTION,
        string="Issued for",
        default="other",
        help="Which part of the trust is consuming this stock. The free-text "
        "note above says WHY; this structured choice lets the Consumption "
        "Value report total spend by purpose (Cows, Pooja, Maintenance, ...). "
        "Defaults to Other so existing flows are never blocked.",
    )

    # Photo capture. Binary + widget="image" gives mobile browsers an
    # <input type="file" accept="image/*" capture="environment"> which
    # opens the camera directly (and is dismissed automatically once the
    # user shoots or cancels). Required when a non-piece UoM is detected.
    photo = fields.Binary(
        string="Item photo",
        attachment=True,
        help="Snap a photo of the item being issued. Required for bulk or liquid items. Attached to the resulting delivery record for audit purposes.",
    )
    photo_required = fields.Boolean(
        compute="_compute_photo_required",
        help="Shown when the planned product is measured by weight or volume (liters, kg, m³, etc.) — a photo is required before the issue can be validated.",
    )

    @api.depends("plan_line_ids.product_id")
    def _compute_photo_required(self):
        # UoM whose category != 'Units' (i.e. measured, not counted).
        unit_cat = self.env.ref("uom.product_uom_categ_unit", raise_if_not_found=False)
        for wiz in self:
            wiz.photo_required = (
                any(
                    ln.product_id.uom_id.category_id != unit_cat
                    for ln in wiz.plan_line_ids
                    if ln.product_id
                )
                if unit_cat
                else False
            )

    def on_barcode_scanned(self, barcode):
        """Auto-plan FIFO deduction when a scan is detected.
        Uses the current `requested_qty` (default 1) — operator can
        adjust qty between scans for bulk items.
        """
        self.last_scan = barcode
        return self.action_plan()

    # ---- Overuse / abuse-prevention -----------------------------------------
    def _enforce_overuse_caps(self):
        """Block any issue that would breach a product's configured caps.

        Two checks per product appearing in plan_line_ids:

          1. **Max per issue** — sum the take across all plan lines for
             this product (a single Scan Issue can plan from multiple
             slots/batches for the same product when FEFO crosses
             batches). If the total > wms_max_per_issue and the cap is
             non-zero, raise UserError naming the cap.

          2. **Daily cap (24h rolling)** — sum every done outbound
             stock.move.line for this product in the last 24 hours,
             add the about-to-issue qty, and compare to wms_daily_cap.
             If the post-issue total would exceed the cap, raise
             UserError naming the cap and the current 24h total.

        Both checks skip when the corresponding cap is 0 (no
        enforcement, the default for every product).
        """
        self.ensure_one()
        if not self.plan_line_ids:
            return

        # Group requested qty by product (FEFO can split across siblings)
        by_product = {}
        for line in self.plan_line_ids:
            by_product.setdefault(line.product_id, 0.0)
            by_product[line.product_id] += line.take

        from datetime import datetime, timedelta

        now = datetime.now()
        cutoff = now - timedelta(hours=24)

        for product, requested_qty in by_product.items():
            tmpl = product.product_tmpl_id
            cap_issue = tmpl.wms_max_per_issue or 0.0
            cap_daily = tmpl.wms_daily_cap or 0.0

            # 1. Per-issue cap
            if cap_issue > 0 and requested_qty > cap_issue:
                raise UserError(
                    "You asked for more %s than is allowed in a single "
                    "issue. You requested %g, but the most you can give "
                    "out in one go is %g. Either ask for less, split this "
                    "into two separate issues, or check with a Manager to "
                    "see if the limit can be changed on the product."
                    % (product.display_name, requested_qty, cap_issue)
                )

            # 2. Daily cap (24h rolling)
            if cap_daily > 0:
                # Count every done outbound move.line for this product
                # in the last 24h. We use stock.move.line.create_date
                # (when the picking was validated) rather than
                # picking_id.date_done so quants that came back via
                # Scan Return aren't double-counted (returns are
                # internal transfers, not outbound).
                # Filter by the immutable wms_is_scan_issue flag the Scan
                # Issue wizard stamps on its picking — robust against any
                # edit or collision in the free-text origin string. Only
                # previous Scan Issue pickings count toward the rolling
                # 24h total; Scan Receipt moves and manual stock
                # adjustments don't.
                lines = (
                    self.env["stock.move.line"]
                    .sudo()
                    .search(
                        [
                            ("product_id", "=", product.id),
                            ("state", "=", "done"),
                            ("create_date", ">=", cutoff),
                            ("picking_id.wms_is_scan_issue", "=", True),
                        ]
                    )
                )
                # UoM-aware: quantity_product_uom is each line's done qty
                # already expressed in the product's reference UoM, so a cap in
                # (say) kilograms isn't breached by lines recorded in grams.
                used_24h = sum(lines.mapped("quantity_product_uom"))
                projected = used_24h + requested_qty
                if projected > cap_daily:
                    raise UserError(
                        "You've reached the daily limit for %s. You've "
                        "already given out %g in the last 24 hours. If "
                        "you issue %g more now, the total will be %g — "
                        "over the daily limit of %g. Wait a few hours and "
                        "try again, or ask a Manager to increase the "
                        "daily limit for this product."
                        % (
                            product.display_name,
                            used_24h,
                            requested_qty,
                            projected,
                            cap_daily,
                        )
                    )

    def action_plan(self):
        self.ensure_one()
        if not self.last_scan:
            raise UserError(
                "Scan a product barcode before planning the issue. "
                "The system needs to know what you want to give out."
            )
        info = self.env["wms.barcode.alias"].resolve(self.last_scan)
        if info.get("kind") not in ("product", "alias", "lot"):
            raise UserError(
                "That barcode isn't linked to any product in the "
                "warehouse. Make sure you scanned the right label, or "
                "ask a Manager to check if the barcode is set up "
                "correctly."
            )

        product = info["product"]
        qty = self.requested_qty * info.get("units", 1.0)

        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            product.id,
            qty,
            parent_location_id=self.warehouse_id.lot_stock_id.id,
        )

        # Was FEFO used? Decide the same way find_oldest_quants_for_product
        # does, so the feedback text matches the planner's behaviour.
        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        kind = product.product_tmpl_id.wms_product_kind
        used_fefo = (kind in EXPIRY_SENSITIVE_KINDS) or bool(
            product.product_tmpl_id.wms_expiry_date
        )

        # Clear previous plan
        self.plan_line_ids.unlink()
        for quant, take in plan:
            # Every planned quant belongs to the scanned product's template
            # (no cross-product widening), so picked is the scanned product.
            picked = quant.product_id
            self.env["wms.scan.issue.plan"].create(
                {
                    "wizard_id": self.id,
                    "product_id": picked.id,
                    "quant_id": quant.id,
                    "location_id": quant.location_id.id,
                    "in_date": quant.in_date,
                    "expiry_date": picked.product_tmpl_id.wms_expiry_date,
                    "available": quant.quantity - quant.reserved_quantity,
                    "take": take,
                }
            )
        self.short_qty = missing

        # Build a clear feedback line. When the warehouse can't satisfy
        # the requested quantity, surface a STOCK OUT message so the
        # operator knows immediately to wait for a return or alert the
        # Admin — not a cryptic "short by 5".
        rule = "FEFO" if used_fefo else "FIFO"
        if not plan and missing:
            self.feedback = (
                "⚠ STOCK OUT — no %s available anywhere in the warehouse. "
                "This product can only come back through Scan Return, or "
                "an Administrator needs to add stock via Scan Receipt."
            ) % product.display_name
        elif missing:
            self.feedback = (
                "⚠ Only %s × %s on hand (%s plan) — that's %s less than "
                "you asked for. Reduce the quantity, or wait for the rest "
                "to come back via Scan Return."
            ) % (qty - missing, product.display_name, rule, missing)
        elif used_fefo:
            # Make it obvious when the planner has crossed batches so the
            # keeper doesn't think the wizard misread their scan.
            picked_names = {ln.product_id.display_name for ln in self.plan_line_ids}
            if len(picked_names) > 1 or (picked_names and product.display_name not in picked_names):
                self.feedback = (
                    "FEFO: planned %s × %s — taking from earlier-expiring "
                    "batch(es): %s. Pick from the slot(s) below."
                ) % (qty, product.display_name, ", ".join(sorted(picked_names)))
            else:
                self.feedback = (
                    "FEFO: planned %s × %s across %d slot(s) — earliest expiry first."
                    % (
                        qty,
                        product.display_name,
                        len(plan),
                    )
                )
        else:
            self.feedback = "Planned %s × %s across %d slot(s)." % (
                qty,
                product.display_name,
                len(plan),
            )
        return self._reopen()

    def action_validate(self):
        self.ensure_one()
        # ---- Idempotency: never issue twice ---------------------------------
        # A double-click on Validate, or a page refresh that re-POSTs the
        # form, would otherwise create a second picking and deduct the
        # stock again. Once we've created a picking, this wizard is spent —
        # just re-open the delivery that was already made.
        if self.picking_id:
            return self._open_picking()
        if not self.plan_line_ids:
            raise UserError(
                "You haven't chosen what to issue yet. Scan a product "
                "and confirm the slots before validating the issue."
            )
        if self.short_qty:
            raise UserError(
                "The warehouse doesn't have enough stock. You're short "
                "by %s. Either wait for stock to come back through Scan "
                "Return, or ask for less now and complete the rest "
                "later." % self.short_qty
            )
        if self.photo_required and not self.photo:
            raise UserError(
                "This product is measured by weight or volume. Take a "
                "photo of what you're issuing and attach it before you "
                "finish — the trust needs proof of measured items."
            )
        # ---- Concurrency: serialize issues of the same product --------------
        # Take a short row lock on each product before the daily-cap read and
        # the reservation. Two keepers issuing the same product now run one
        # after the other instead of overlapping, so neither the rolling-24h
        # cap check nor the oldest-stock pick can be raced. The lock is held
        # only until this transaction commits (a second or two) and products
        # are locked in id order so concurrent multi-product issues can't
        # deadlock. Different products never contend.
        product_ids = sorted(set(self.plan_line_ids.mapped("product_id").ids))
        if product_ids:
            self.env.cr.execute(
                "SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                (tuple(product_ids),),
            )
        # ---- Overuse / abuse-prevention checks ------------------------------
        # Hard-block any single-issue qty over wms_max_per_issue and any
        # request that would push the rolling-24h total over wms_daily_cap.
        # 0 on either field = no cap. See product.template for the rationale.
        # Now race-safe: it runs inside the per-product lock above.
        self._enforce_overuse_caps()

        # Pick a picking type via warehouse-level m2o so we don't get bitten
        # by Odoo 19 archiving the internal type for 1-step warehouses.
        if self.destination_id.usage == "customer":
            picking_type = self.warehouse_id.out_type_id
        else:
            picking_type = self.warehouse_id.int_type_id
        if not picking_type:
            raise UserError(
                "Warehouse %s isn't set up to issue stock this way. Ask "
                "a Manager to check the warehouse settings in Odoo and "
                "enable the right operation type." % self.warehouse_id.display_name
            )
        if not picking_type.active:
            picking_type.sudo().active = True

        # Group plan lines by source so we make one move per (product, source).
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.warehouse_id.lot_stock_id.id,
                "location_dest_id": self.destination_id.id,
                "origin": "Barcode FIFO issue",
                # Immutable marker the 24h daily-cap counter filters on
                # (robust replacement for matching the origin string).
                "wms_is_scan_issue": True,
                # Audit-trail fields — who took it, who authorised it,
                # which keeper was on duty.
                "wms_taken_by": (self.taken_by or "").strip(),
                "wms_ordered_by": (self.ordered_by or "").strip(),
                "wms_storekeeper_id": self.storekeeper_id.id,
                "wms_issued_for": self.issued_for,
            }
        )
        for line in self.plan_line_ids:
            move = self.env["stock.move"].create(
                {
                    "description_picking": line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.take,
                    "product_uom": line.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": line.location_id.id,
                    "location_dest_id": self.destination_id.id,
                }
            )
            move._action_confirm()
        picking.action_assign()
        # ---- Concurrency safety: only issue what we could actually reserve --
        # action_assign reserves against LIVE quants (Odoo row-locks them).
        # If another keeper emptied a planned slot between planning and now,
        # the move won't be fully assigned. Abort cleanly — raising here rolls
        # back the whole transaction (no half-made picking, no negative stock)
        # — instead of blindly forcing the line quantity and deducting stock
        # that isn't on the shelf.
        unassigned = picking.move_ids.filtered(lambda m: m.state != "assigned")
        if unassigned:
            raise UserError(
                "Another keeper took some of this stock while you were "
                "finishing up, so it can no longer be issued in full. "
                "Nothing was issued. Please scan again to plan against "
                "what's left on the shelf."
            )
        for move in picking.move_ids:
            for ml in move.move_line_ids:
                if not ml.quantity:
                    ml.quantity = ml.quantity_product_uom or move.product_uom_qty
                # FPAT High: snapshot unit cost ONTO the move line so the
                # Consumption Value report reads a frozen number. The previous
                # view joined to live product.standard_price which retroactively
                # rewrote past months when the cost changed.
                ml.wms_unit_cost_at_done = ml.product_id.standard_price or 0.0
        picking.button_validate()
        # Record the picking so a re-submit is a no-op (idempotency guard).
        self.picking_id = picking.id

        # Audit-trail message. Goes into the picking's history so the
        # Admin can scroll back through it later. Includes the Odoo
        # login (env.user) too — the on-duty roster name covers the
        # actual human; the login records which Odoo account was used.
        # Markup() so Odoo 19 renders the HTML instead of escaping it.
        audit_body = Markup(
            "<p><b>Issued.</b> "
            "Taken by <b>%s</b>; ordered by <b>%s</b>; "
            "Store Keeper on duty: <b>%s</b>; "
            "logged in as: <b>%s</b>.</p>"
            "<p><b>Reason / usage note:</b><br/>%s</p>"
        ) % (
            picking.wms_taken_by or "(unspecified)",
            picking.wms_ordered_by or "(unspecified)",
            picking.wms_storekeeper_id.name or "(unknown)",
            self.env.user.display_name or "(system)",
            (self.usage_note or "").replace("\n", "<br/>") or "(missing — should never happen)",
        )
        picking.message_post(
            body=audit_body,
            subject="Issue audit",
            message_type="notification",
        )
        # Copy usage_note onto the picking's `note` so it shows up in
        # the form view, not just the chatter.
        if "note" in picking._fields:
            picking.note = self.usage_note

        # Attach the photo (if any) so it's visible from the picking's
        # history and survives in the audit trail. We always store it
        # when present, not only when photo_required is True — operators
        # may want proof even for unit items.
        if self.photo:
            self.env["ir.attachment"].create(
                {
                    "name": "issue-photo-%s.jpg" % picking.name,
                    "datas": self.photo,
                    "res_model": "stock.picking",
                    "res_id": picking.id,
                    "mimetype": "image/jpeg",
                }
            )
            picking.message_post(
                body="Operator photo attached at issue.",
                attachment_ids=self.env["ir.attachment"]
                .search(
                    [
                        ("res_model", "=", "stock.picking"),
                        ("res_id", "=", picking.id),
                        ("name", "=", "issue-photo-%s.jpg" % picking.name),
                    ]
                )
                .ids,
            )

        return self._open_picking()

    def _open_picking(self):
        """Open the delivery this issue created (also the no-op target a
        double-submit lands on)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Scan Issue (FIFO)",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class WmsScanIssuePlan(models.TransientModel):
    _name = "wms.scan.issue.plan"
    _description = "Planned deduction line (FIFO / FEFO)"
    # No fixed _order: when the wizard does FEFO, lines are written in
    # expiry order; for plain FIFO they're written in in_date order.
    # Sorting in SQL by either column would re-shuffle the wrong cases.

    wizard_id = fields.Many2one("wms.scan.issue", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", required=True)
    quant_id = fields.Many2one("stock.quant")
    location_id = fields.Many2one("stock.location", string="Slot")
    in_date = fields.Datetime()
    expiry_date = fields.Date(
        string="Expires",
        help="Batch expiry date for medicine / feed / fluid / pooja. "
        "When set, the planner sorts by this date (FEFO) — earliest "
        "expiry first — instead of arrival date.",
    )
    available = fields.Float()
    take = fields.Float()

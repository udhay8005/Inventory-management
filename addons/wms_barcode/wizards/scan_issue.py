from markupsafe import Markup, escape
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
        string="Used by / area",
        required=True,
        domain=[("usage", "in", ("customer", "production", "internal"))],
        default=lambda s: s._default_destination_id(),
        help="Where the issued stock goes. Defaults to the trust's "
        "'Trust internal use' location since the trust uses inventory "
        "internally rather than selling it. Most issues leave this as-is; "
        "change it only to charge a specific area (Cow Shed, Pooja Room, "
        "etc.) on the day, without changing the default.",
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

    last_scan = fields.Char(string="Scan here")
    requested_qty = fields.Float(string="Quantity", default=1.0)
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
        help="Optional — name of the person who authorised this issue "
        "(the Manager / cow-care lead / project owner). Leave blank if it's "
        "the same as the keeper or not tracked for this issue.",
    )
    storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        required=True,
        domain=[("active", "=", True)],
        default=lambda s: s._default_storekeeper_id(),
        help="The actual human running the desk right now. Defaults to the "
        "roster entry linked to your login. Pick from the roster the Admin "
        "maintains under Configuration → Store Keepers. If the name you want "
        "isn't here, ask the Admin to add it before validating.",
    )

    @api.model
    def _default_storekeeper_id(self):
        """Pre-select the roster entry linked to the logged-in user so the
        keeper doesn't re-pick themselves on every issue. Empty when the user
        isn't on the roster (e.g. the shared desk login) - then the keeper
        picks who is at the desk, exactly as before."""
        return self.env["wms.storekeeper"].search(
            [("user_id", "=", self.env.uid), ("active", "=", True)], limit=1
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
        help="Legacy structured purpose. Now derived from the Department on "
        "validate (department.legacy_issued_for) so old reports/searches keep "
        "working; the Department field below is the primary capture. Hidden in "
        "the form, kept on the model for the derivation fallback.",
    )

    # ---- Issue dimensions (F1) -------------------------------------------
    # Structured Department / Purpose / Animal. Department is required (the
    # seeded 'Other' department is the default so the wizard is never
    # blocked — mirrors the old issued_for='other' default); Purpose and
    # Animal are optional. Copied onto the resulting picking at validate.
    department_id = fields.Many2one(
        "wms.department",
        string="Department",
        required=True,
        default=lambda s: s._default_department_id(),
        help="Which department / cost centre is consuming this stock "
        "(Gaushala, Veterinary, Dairy, ...). Defaults to 'Other' so an issue "
        "is never blocked. Drives the Consumption Value report breakdown and "
        "the legacy 'Issued for' column.",
    )
    purpose_id = fields.Many2one(
        "wms.purpose",
        string="Purpose / reason",
        help="The structured reason for this issue (routine feed, treatment, "
        "repair, ...). Optional — the free-text note above always captures the "
        "detail.",
    )
    animal_id = fields.Many2one(
        "wms.animal",
        string="Animal / cow",
        help="The specific animal this issue is for, when it applies "
        "(e.g. a treatment for a named cow). Optional.",
    )

    @api.model
    def _default_department_id(self):
        """Default to the seeded 'Other' department so the wizard is never
        blocked (mirrors the legacy ``issued_for`` default of ``'other'``).

        Returns an empty recordset if the WMS data file hasn't loaded yet
        (e.g. mid-install); the operator then picks a department manually.
        """
        return self.env.ref("wms_location.dept_other", raise_if_not_found=False)

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

    # ---- Manager-approval gate (F4 + F5) ---------------------------------
    # When a planned issue is high-value (F5) or re-requests a product the
    # same department took too recently (F4), it can't go through inline —
    # the keeper must type a justification and it routes to a Manager. The
    # reason box is hidden until ``needs_approval`` is True (a lightweight
    # pre-check run when the plan is built); the HARD gate re-checks inside
    # the per-product lock in action_validate.
    keeper_reason = fields.Text(
        string="Reason for the Manager",
        help="Only needed when this issue is held for approval (high value, "
        "or the same department requested this item too recently). Explain "
        "why it should still go through; a Manager reviews it before any "
        "stock moves.",
    )
    needs_approval = fields.Boolean(
        compute="_compute_needs_approval",
        help="True when the current plan would be held for a Manager's "
        "approval (high value or requested too soon). Drives whether the "
        "reason box is shown.",
    )

    @api.depends(
        "plan_line_ids.product_id",
        "plan_line_ids.take",
        "department_id",
    )
    def _compute_needs_approval(self):
        """Lightweight, NON-locking pre-check so the reason box appears
        proactively. The authoritative gate still runs inside the
        per-product FOR UPDATE lock in action_validate."""
        for wiz in self:
            if not wiz._approval_gate_enabled():
                wiz.needs_approval = False
                continue
            wiz.needs_approval = bool(wiz._check_high_value() or wiz._check_min_life()[0])

    @api.depends("plan_line_ids.product_id")
    def _compute_photo_required(self):
        # Arm the photo gate for "measured, not counted" products — those
        # issued by weight / volume / length (kg, Litre, Metre) rather than
        # by the whole piece.
        #
        # Why not category_id != Units category? Odoo 19 CE dropped UoM
        # categories — ``uom.product_uom_categ_unit`` resolves to None — so
        # the old category test was always falsy and the photo gate was
        # INERT (no measured product ever required a photo). UoMs are now
        # organised as ``relative_uom_id`` parent chains, so we classify by
        # walking each UoM to its chain root (see ``_uom_is_measured``):
        # anything rooted in the Units UoM — Units itself AND bundles of it
        # (Pack of 6, Dozens, or a custom child) — is COUNTED and stays
        # photo-free; everything else (Volume / Weight / Length / ... chains)
        # is MEASURED and requires a photo.
        for wiz in self:
            wiz.photo_required = any(
                self._uom_is_measured(ln.product_id.uom_id)
                for ln in wiz.plan_line_ids
                if ln.product_id
            )

    def _uom_is_measured(self, uom):
        """True when ``uom`` measures by weight / volume / length (kg, Litre,
        Metre, ...) rather than counting whole pieces.

        Counted UoMs are the Units chain — the ``uom.product_uom_unit`` root
        plus any bundle of it (Pack of 6, Dozens, or a custom child) —
        identified by walking ``relative_uom_id`` to the root and checking it
        is the Units UoM. Returns False (gate disarmed, fail-open) when the
        Units UoM can't be resolved or the product carries no UoM, matching
        the prior "never block on an un-classifiable product" behaviour.
        """
        units_root = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        if not units_root or not uom:
            return False
        node = uom
        seen = set()  # cycle guard — the FK can't loop, but stay defensive
        while node and node.id not in seen:
            if node == units_root:
                return False  # rooted in Units -> counted, no photo
            seen.add(node.id)
            node = node.relative_uom_id
        return True  # rooted outside the Units chain -> measured, photo required

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
        # Delegate to the product-keyed core so the deferred approval path
        # (wms.issue.approval.action_approve) enforces the SAME caps.
        self._enforce_overuse_caps_for(by_product)

    @api.model
    def _enforce_overuse_caps_for(self, by_product):
        """Core cap enforcement, keyed by ``{product: requested_qty}``.

        Shared by the inline path (action_validate -> _enforce_overuse_caps)
        and the deferred approval path
        (wms.issue.approval.action_approve), so the per-issue + rolling-24h
        daily caps are enforced identically whether an issue goes through
        immediately or is approved later. The approval path in particular
        MUST re-run this: stock that was within the daily cap when a request
        was held can be over the cap by the time a Manager approves it (other
        issues consumed the 24h window in between) — without this, the
        approval is a back door around the daily cap.

        Callers MUST hold a per-product FOR UPDATE lock first (both do) so the
        rolling-24h read can't be raced.
        """
        if not by_product:
            return

        from datetime import timedelta

        # UTC, to align with the UTC `create_date` column. datetime.now() is
        # server-LOCAL; on the IST (UTC+5:30) deploy it shrank the rolling
        # "24h" window by the offset (~18.5h), so issues 18.5-24h ago dropped
        # out and the cap failed OPEN. fields.Datetime.now() keeps the cutoff
        # in UTC so the window is a true 24h regardless of server timezone.
        now = fields.Datetime.now()
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
                            # An undone (reversed) issue nets zero consumption,
                            # so it must not count toward the rolling 24h cap.
                            ("picking_id.wms_reversed_by_id", "=", False),
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

    # ---- Returnable items (F3) ----------------------------------------------
    def _expected_return_date(self):
        """Compute the expected-return date for this issue, or False.

        Returnable items are expected back within an SLA: today + the
        product's ``expected_return_days``, falling back to the global
        System Parameter ``wms_reports.default_return_days`` when the
        product leaves it at 0. When more than one returnable product is
        planned we take the LONGEST per-product window so the alert never
        fires early on the slowest item.

        Returns a ``date`` when at least one planned product is
        returnable, or False otherwise (a non-returnable issue carries no
        expected-return date). Advisory only — never blocks the issue.
        """
        self.ensure_one()
        returnable = self.plan_line_ids.filtered(
            lambda ln: ln.product_id and ln.product_id.wms_is_returnable
        )
        if not returnable:
            return False
        try:
            fallback = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("wms_reports.default_return_days", "7")
                or 0
            )
        except (TypeError, ValueError):
            fallback = 7
        days = max((ln.product_id.expected_return_days or fallback) for ln in returnable)
        if days <= 0:
            return False
        from datetime import timedelta

        return fields.Date.context_today(self) + timedelta(days=days)

    # ---- Manager-approval gate (F4 + F5) ---------------------------------
    def _approval_gate_enabled(self):
        """Master switch. ``wms_barcode.issue_approval_enabled`` != '1'
        bypasses the whole gate (issues validate inline as before) — a cheap
        early-exit, like ``wms_location.enforce_capacity``."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("wms_barcode.issue_approval_enabled", "1")
            == "1"
        )

    def _check_high_value(self):
        """F5 — True when the planned issue's total value exceeds the
        high-value threshold.

        Value = sum(take x standard_price). Python's ``standard_price``
        resolves the company automatically. A non-numeric / missing
        threshold is treated as disabled (try/except → 0), never a crash.
        """
        self.ensure_one()
        if not self.plan_line_ids:
            return False
        try:
            threshold = float(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("wms_barcode.high_value_threshold", "5000")
                or 0
            )
        except (TypeError, ValueError):
            return False  # bad param value → gate disabled, no crash
        if threshold <= 0:
            return False
        return self._issue_value() > threshold

    def _issue_value(self):
        """Frozen-at-call total value of the current plan."""
        self.ensure_one()
        return sum(
            line.take * (line.product_id.standard_price or 0.0) for line in self.plan_line_ids
        )

    def _check_min_life(self):
        """F4 — has the SAME department issued the SAME product within its
        minimum re-request interval?

        Per planned product: window = product.wms_min_life_days, or the
        global ``wms_location.default_min_life_days`` fallback when the
        product leaves it at 0. window <= 0 means no guard. If a done Scan
        Issue done move-line for this department + product exists inside the
        window (same shape as ``_enforce_overuse_caps``; race-safe inside
        the per-product lock), the guard trips.

        Returns ``(tripped, product, last_date)``. ``getattr`` guards the
        product field so this never crashes if the wms_location side hasn't
        loaded yet (defensive — the field is shipped there by the contract).
        """
        self.ensure_one()
        if not (self.plan_line_ids and self.department_id):
            return (False, self.env["product.product"], False)
        try:
            global_default = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("wms_location.default_min_life_days", "0")
                or 0
            )
        except (TypeError, ValueError):
            global_default = 0

        from datetime import timedelta

        # UTC — same reason as _enforce_overuse_caps: server-local time vs the
        # UTC create_date column shrank the min-life window by the TZ offset,
        # letting a too-soon re-request slip the approval gate near the edge.
        now = fields.Datetime.now()
        # One product per planned product (FEFO can split across siblings).
        products = self.plan_line_ids.mapped("product_id")
        for product in products:
            window = getattr(product, "wms_min_life_days", 0) or global_default
            if window <= 0:
                continue
            cutoff = now - timedelta(days=window)
            line = (
                self.env["stock.move.line"]
                .sudo()
                .search(
                    [
                        ("product_id", "=", product.id),
                        ("state", "=", "done"),
                        ("create_date", ">=", cutoff),
                        ("picking_id.wms_is_scan_issue", "=", True),
                        ("picking_id.wms_department_id", "=", self.department_id.id),
                        # An undone (reversed) issue didn't really happen — exclude
                        # it from the min-life re-request gate.
                        ("picking_id.wms_reversed_by_id", "=", False),
                    ],
                    order="create_date desc",
                    limit=1,
                )
            )
            if line:
                return (True, product, line.create_date)
        return (False, self.env["product.product"], False)

    def _create_approval(self, reason_high_value, reason_min_life, min_life_product, min_life_date):
        """Snapshot the held request onto a persistent ``wms.issue.approval``
        in state ``pending``. NOTHING is issued — a Manager replays it later.

        ``issue_value`` is FROZEN here, never recomputed (FPAT lesson)."""
        self.ensure_one()
        line_vals = [
            (
                0,
                0,
                {
                    "product_id": line.product_id.id,
                    "location_id": line.location_id.id,
                    "quant_id": line.quant_id.id,
                    "take": line.take,
                    "expiry_date": line.expiry_date,
                },
            )
            for line in self.plan_line_ids
        ]
        approval = self.env["wms.issue.approval"].create(
            {
                "state": "pending",
                "reason_high_value": reason_high_value,
                "reason_min_life": reason_min_life,
                "issue_value": self._issue_value(),
                "keeper_reason": self.keeper_reason,
                "min_life_product_id": min_life_product.id if min_life_product else False,
                "min_life_last_date": min_life_date or False,
                "warehouse_id": self.warehouse_id.id,
                "destination_id": self.destination_id.id,
                "department_id": self.department_id.id,
                "purpose_id": self.purpose_id.id or False,
                "animal_id": self.animal_id.id or False,
                "taken_by": (self.taken_by or "").strip(),
                "ordered_by": (self.ordered_by or "").strip(),
                "storekeeper_id": self.storekeeper_id.id,
                "usage_note": self.usage_note,
                "expected_return_date": self._expected_return_date() or False,
                "photo": self.photo,
                "line_ids": line_vals,
            }
        )
        approval.notify_managers_held()
        return approval

    def _open_approval(self, approval):
        """Open the held approval read-only so the keeper sees it went to a
        Manager (the keeper ACL is read+create only — no Approve button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Issue held for approval",
            "res_model": "wms.issue.approval",
            "res_id": approval.id,
            "view_mode": "form",
        }

    def action_plan(self):
        self.ensure_one()
        # Reject a non-positive quantity up front with a clear message. Without
        # this, qty<=0 slips into the planner (which returns an empty plan) and
        # is then mis-described downstream as a fake success ("Planned 0 x ...")
        # for 0, or a bogus "STOCK OUT" for a negative — even when the product
        # is fully in stock. Mirrors the receipt line's CHECK(quantity > 0).
        if self.requested_qty <= 0:
            raise UserError(
                "Quantity must be greater than zero. Enter how many units "
                "you want to issue (the default is 1)."
            )
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

        # Build a clear feedback line. The planner removes OLDEST stock first
        # (FIFO — see stock.quant._wms_sorted_for_removal). When the warehouse
        # can't satisfy the requested quantity, surface a STOCK OUT message so
        # the operator knows immediately to wait for a return or alert the
        # Admin — not a cryptic "short by 5".
        if not plan and missing:
            self.feedback = (
                "⚠ STOCK OUT — no %s available anywhere in the warehouse. "
                "This product can only come back through Scan Return, or "
                "an Administrator needs to add stock via Scan Receipt."
            ) % product.display_name
        elif missing:
            self.feedback = (
                "⚠ Only %s × %s on hand (oldest stock first) — that's %s less "
                "than you asked for. Reduce the quantity, or wait for the rest "
                "to come back via Scan Return."
            ) % (qty - missing, product.display_name, missing)
        else:
            self.feedback = "Planned %s × %s across %d slot(s) — oldest stock first." % (
                qty,
                product.display_name,
                len(plan),
            )
        return self._reopen()

    def action_validate(self):
        self.ensure_one()
        # ---- Idempotency: never issue twice ---------------------------------
        # FPAT High: this MUST hold under real concurrency (two parallel RPC
        # submits of the same wizard id). The previous pure-ORM check was
        # cached and pre-lock, so two parallel calls both saw picking_id=NULL
        # and both proceeded to create. We now SELECT FOR UPDATE the wizard
        # row itself before doing anything else - the second caller waits,
        # sees the now-populated picking_id, and short-circuits.
        self.env.cr.execute(
            "SELECT picking_id FROM wms_scan_issue WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        row = self.env.cr.fetchone()
        if row and row[0]:
            # Refresh the recordset so subsequent code sees the picking.
            self.invalidate_recordset(["picking_id"])
            return self._open_picking()
        # In-Python fast-path for the common single-process case (avoids the
        # round-trip to _open_picking when picking_id was set by an earlier
        # write in the same env).
        if self.picking_id:
            return self._open_picking()
        if not self.plan_line_ids:
            raise UserError(
                "There's nothing planned to issue. Scan a product that has "
                "stock on hand and set a quantity above zero, then confirm "
                "the slots before validating."
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

        # ---- Manager-approval gate (F4 + F5) --------------------------------
        # Inside the per-product lock (after the hard caps) so the min-life
        # query is race-safe, exactly like _enforce_overuse_caps. The master
        # switch lets the whole gate be turned off cheaply. When tripped, the
        # request is SNAPSHOTTED to a persistent wms.issue.approval (pending)
        # and NOTHING is issued — a Manager replays it later. Hard caps stay
        # HARD blocks above; this is the new SOFT (reason + approval) path.
        if self._approval_gate_enabled():
            high_value = self._check_high_value()
            min_life, ml_product, ml_date = self._check_min_life()
            if high_value or min_life:
                if not (self.keeper_reason or "").strip():
                    raise UserError(
                        "This issue needs a Manager's approval "
                        "(it's high value, or your department requested this "
                        "item too recently). Type the reason in the "
                        "'Reason for the Manager' box below and submit again — "
                        "it will be sent to a Manager to approve. No stock has "
                        "moved."
                    )
                approval = self._create_approval(
                    reason_high_value=high_value,
                    reason_min_life=min_life,
                    min_life_product=ml_product,
                    min_life_date=ml_date,
                )
                # Do NOT create the picking — a Manager replays it on approve.
                return self._open_approval(approval)

        # Returnable items (F3): when any planned product is returnable,
        # stamp the date it's expected back so the overdue-returns alert
        # and the Returns-due report can track it. wms_returned stays at
        # its False default until Scan Return marks it back in.
        expected_return_date = self._expected_return_date()

        # Group plan lines by source so we make one move per (product, source).
        # Normalise the plan into the shared (product, [(quant, take)]) shape
        # the helper consumes — the SAME shape action_approve re-plans into.
        replanned = []
        for product in self.plan_line_ids.mapped("product_id"):
            pairs = [
                (line.quant_id, line.take)
                for line in self.plan_line_ids
                if line.product_id == product
            ]
            replanned.append((product, pairs))

        picking = self._build_issue_picking(
            warehouse=self.warehouse_id,
            destination=self.destination_id,
            replanned=replanned,
            origin="Barcode FIFO issue",
            audit_vals={
                "wms_taken_by": (self.taken_by or "").strip(),
                "wms_ordered_by": (self.ordered_by or "").strip(),
                "wms_storekeeper_id": self.storekeeper_id.id,
                "wms_department_id": self.department_id.id,
                "wms_purpose_id": self.purpose_id.id or False,
                "wms_animal_id": self.animal_id.id or False,
                "wms_issued_for": self.department_id.legacy_issued_for
                or self.issued_for
                or "other",
                "wms_expected_return_date": expected_return_date,
            },
            usage_note=self.usage_note,
        )
        # Record the picking so a re-submit is a no-op (idempotency guard).
        self.picking_id = picking.id

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

    @api.model
    def _build_issue_picking(
        self, warehouse, destination, replanned, origin, audit_vals, usage_note
    ):
        """Create + validate the outbound picking for a Scan Issue.

        Shared by BOTH the inline auto-allow path (action_validate) and the
        deferred approval path (wms.issue.approval.action_approve), so the
        move/assign/validate/cost-snapshot/chatter logic lives in ONE place.

        :param warehouse: the stock.warehouse to issue from.
        :param destination: the destination stock.location.
        :param replanned: a list of ``(product, [(quant, take), ...])`` —
            one entry per product, each with the source quant(s) and qty.
            The source location is read from each quant.
        :param origin: the picking origin. MUST start ``'Barcode'`` so the
            audit-triplet DB CHECK + @api.constrains fire and enforce
            wms_storekeeper_id — both the inline and the approved origins do.
        :param audit_vals: dict of wms_* audit fields written onto the
            picking create dict (wms_taken_by / wms_ordered_by /
            wms_storekeeper_id / dimensions / wms_issued_for /
            wms_expected_return_date).
        :param usage_note: the reason/usage note for the chatter + note.
        :returns: the validated stock.picking.

        Preserves the original inline behaviour exactly: the
        wms_is_scan_issue marker, the not-fully-assigned abort (no
        half-picking / no negative stock), and the frozen
        wms_unit_cost_at_done snapshot onto each move line.
        """
        # Pick a picking type via warehouse-level m2o so we don't get bitten
        # by Odoo 19 archiving the internal type for 1-step warehouses.
        if destination.usage == "customer":
            picking_type = warehouse.out_type_id
        else:
            picking_type = warehouse.int_type_id
        if not picking_type:
            raise UserError(
                "Warehouse %s isn't set up to issue stock this way. Ask "
                "a Manager to check the warehouse settings in Odoo and "
                "enable the right operation type." % warehouse.display_name
            )
        if not picking_type.active:
            picking_type.sudo().active = True

        picking_vals = {
            "picking_type_id": picking_type.id,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": destination.id,
            "origin": origin,
            # Immutable marker the 24h daily-cap counter filters on
            # (robust replacement for matching the origin string).
            "wms_is_scan_issue": True,
        }
        picking_vals.update(audit_vals or {})
        picking = self.env["stock.picking"].create(picking_vals)

        # One move per (product, source slot).
        for product, pairs in replanned:
            for quant, take in pairs:
                move = self.env["stock.move"].create(
                    {
                        "description_picking": product.display_name,
                        "product_id": product.id,
                        "product_uom_qty": take,
                        "product_uom": product.uom_id.id,
                        "picking_id": picking.id,
                        "location_id": quant.location_id.id,
                        "location_dest_id": destination.id,
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

        # Audit-trail message. Goes into the picking's history so the
        # Admin can scroll back through it later. Includes the Odoo
        # login (env.user) too — the on-duty roster name covers the
        # actual human; the login records which Odoo account was used.
        # Markup() so Odoo 19 renders the HTML instead of escaping it.
        # Issue dimensions for the audit trail. Department/Purpose/Animal
        # names are admin-seeded, but escape() defensively so a stray HTML
        # character in a renamed record can never break the chatter markup.
        dims_body = Markup(
            "<p><b>Department:</b> %s; <b>Purpose:</b> %s; <b>Animal:</b> %s.</p>"
        ) % (
            escape(picking.wms_department_id.name or "(unspecified)"),
            escape(picking.wms_purpose_id.name or "(none)"),
            escape(picking.wms_animal_id.name or "(none)"),
        )
        audit_body = (
            Markup(
                "<p><b>Issued.</b> "
                "Taken by <b>%s</b>; ordered by <b>%s</b>; "
                "Store Keeper on duty: <b>%s</b>; "
                "logged in as: <b>%s</b>.</p>"
            )
            % (
                picking.wms_taken_by or "(unspecified)",
                picking.wms_ordered_by or "(unspecified)",
                picking.wms_storekeeper_id.name or "(unknown)",
                self.env.user.display_name or "(system)",
            )
            + dims_body
            + Markup("<p><b>Reason / usage note:</b><br/>%s</p>")
            % ((usage_note or "").replace("\n", "<br/>") or "(missing — should never happen)")
        )
        picking.message_post(
            body=audit_body,
            subject="Issue audit",
            message_type="notification",
        )
        # Copy usage_note onto the picking's `note` so it shows up in
        # the form view, not just the chatter.
        if "note" in picking._fields:
            picking.note = usage_note
        return picking

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
            "name": "Scan Issue",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class WmsScanIssuePlan(models.TransientModel):
    _name = "wms.scan.issue.plan"
    _description = "Planned deduction line (FIFO — oldest arrival first)"
    # No fixed _order: lines are written in the planner's removal order
    # (in_date / FIFO). Sorting in SQL would re-shuffle that intended order.

    wizard_id = fields.Many2one("wms.scan.issue", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", required=True)
    quant_id = fields.Many2one("stock.quant")
    location_id = fields.Many2one("stock.location", string="Slot")
    in_date = fields.Datetime()
    expiry_date = fields.Date(
        string="Expires",
        help="The product's expiry date, shown for awareness. Removal order "
        "is oldest-arrival-first (FIFO); watch the Expiry-Alert report for "
        "items nearing expiry.",
    )
    available = fields.Float()
    take = fields.Float()

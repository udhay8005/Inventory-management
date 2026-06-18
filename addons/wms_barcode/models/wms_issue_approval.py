import logging

from markupsafe import Markup, escape
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class WmsIssueApproval(models.Model):
    """A held Scan Issue awaiting a Manager's approval (F4 + F5).

    The Scan Issue wizard (``wms.scan.issue``) is Transient and gets
    vacuumed, so a held request can't live on it. When an issue trips the
    high-value (F5) or min-life re-request (F4) gate the wizard snapshots
    the whole request onto THIS persistent model in state ``pending`` and
    issues NOTHING. A Manager later opens it from WMS -> Approvals and
    either approves (which replays the picking creation against live stock)
    or rejects (nothing issued).

    Append-only / auditable (perm_unlink=0 for everyone, mirrors
    ``wms.damage``). ``issue_value`` is a FROZEN snapshot taken at request
    time, never a live compute (FPAT lesson: a computed value silently
    re-rates the past when standard_price changes).
    """

    _name = "wms.issue.approval"
    _description = "Held Scan Issue awaiting manager approval"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default="/", readonly=True, copy=False, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )

    # ---- Why was this held? ---------------------------------------------
    reason_high_value = fields.Boolean(
        string="High value",
        readonly=True,
        help="Set when the issue's total value exceeded the high-value "
        "threshold (System Parameter wms_barcode.high_value_threshold).",
    )
    reason_min_life = fields.Boolean(
        string="Requested too soon",
        readonly=True,
        help="Set when the same department re-requested the same product "
        "within its minimum re-request interval (wms_min_life_days, or the "
        "global wms_location.default_min_life_days fallback).",
    )
    issue_value = fields.Float(
        string="Issue value",
        readonly=True,
        copy=False,
        help="Frozen snapshot of sum(take x unit cost) at the moment the "
        "request was held. NEVER recomputed — a later cost change must not "
        "rewrite what this issue was worth when it was requested (FPAT "
        "lesson, same as wms.damage.damage_value).",
    )
    keeper_reason = fields.Text(
        string="Keeper's justification",
        required=True,
        help="The reason the keeper typed when the issue was held, "
        "explaining why it should still go through despite tripping the "
        "high-value / too-soon gate. Shown to the Manager who approves.",
    )
    min_life_product_id = fields.Many2one(
        "product.product",
        string="Too-soon product",
        readonly=True,
        help="The product whose re-request tripped the min-life guard.",
    )
    min_life_last_date = fields.Datetime(
        string="Last issued (same dept)",
        readonly=True,
        help="When this department last issued the too-soon product.",
    )

    # ---- Decision / result anchor ---------------------------------------
    approver_id = fields.Many2one(
        "res.users",
        string="Approved / rejected by",
        readonly=True,
        copy=False,
    )
    decision_date = fields.Datetime(readonly=True, copy=False)
    picking_id = fields.Many2one(
        "stock.picking",
        string="Issued delivery",
        readonly=True,
        copy=False,
        help="The delivery created when this request was approved. Set once, "
        "under a row lock, so a double / concurrent approve can never issue "
        "the same stock twice — the second attempt just re-opens it.",
    )

    # ---- Request snapshot (replayed at approval time) -------------------
    warehouse_id = fields.Many2one("stock.warehouse", readonly=True)
    destination_id = fields.Many2one("stock.location", readonly=True)
    department_id = fields.Many2one("wms.department", string="Department", readonly=True)
    purpose_id = fields.Many2one("wms.purpose", string="Purpose / reason", readonly=True)
    animal_id = fields.Many2one("wms.animal", string="Animal / cow", readonly=True)
    taken_by = fields.Char(string="Taken by", readonly=True)
    ordered_by = fields.Char(string="Ordered by", readonly=True)
    storekeeper_id = fields.Many2one(
        "wms.storekeeper", string="Store Keeper on duty", readonly=True
    )
    usage_note = fields.Text(string="Reason / usage note", readonly=True)
    expected_return_date = fields.Date(string="Expected return", readonly=True)
    photo = fields.Binary(
        string="Item photo",
        attachment=True,
        readonly=True,
        help="The keeper's photo, carried through approval onto the "
        "resulting delivery's audit trail.",
    )
    line_ids = fields.One2many(
        "wms.issue.approval.line",
        "approval_id",
        string="Planned lines",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") in ("/", False):
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.issue.approval") or "/"
        return super().create(vals_list)

    # ---- State machine ---------------------------------------------------
    def _ensure_can_decide(self):
        """Defense-in-depth manager re-check (mirrors the spec's
        in-method has_group check). The Approve/Reject buttons are already
        gated in the view, and the keeper ACL is read+create only, but a
        forced RPC call must still be refused for a non-manager."""
        self.ensure_one()
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise AccessError(
                "Only a WMS Manager can approve or reject a held issue. "
                "Ask a Manager to review this request."
            )

    def action_approve(self):
        """Approve the held issue: re-plan against live stock and replay
        the exact picking-creation logic the inline path uses.

        Idempotent under concurrency: a SELECT ... FOR UPDATE on this
        approval row (mirroring the wizard's own row-lock) serialises a
        double / concurrent approve. The second caller waits, sees
        ``picking_id`` already set, and short-circuits to open it — exactly
        one picking is ever created.
        """
        self.ensure_one()
        self._ensure_can_decide()
        # Idempotency lock: serialise concurrent approves on this exact row.
        self.env.cr.execute(
            "SELECT picking_id FROM wms_issue_approval WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        row = self.env.cr.fetchone()
        if row and row[0]:
            self.invalidate_recordset(["picking_id"])
            return self.action_open_picking()
        if self.picking_id:
            return self.action_open_picking()
        if self.state != "pending":
            raise UserError(
                "This request has already been %s — there is nothing left "
                "to approve." % dict(self._fields["state"].selection).get(self.state, self.state)
            )
        if not self.line_ids:
            raise UserError("This request has no planned lines to issue.")

        # ---- Re-plan against LIVE stock -------------------------------------
        # Quants may have moved since the request was held. Re-run the FIFO/
        # FEFO planner per product against current stock; if it no longer
        # covers the requested qty, abort cleanly (NO half-picking) so the
        # Manager rejects and asks the keeper to scan again.
        StockLocation = self.env["stock.location"]
        parent_location_id = self.warehouse_id.lot_stock_id.id if self.warehouse_id else False
        # Group requested take by product (a request can span sibling slots).
        by_product = {}
        for line in self.line_ids:
            by_product.setdefault(line.product_id, 0.0)
            by_product[line.product_id] += line.take

        # ---- Re-enforce overuse caps as-of-now ------------------------------
        # The per-issue + rolling-24h daily caps were checked when the request
        # was HELD, but other issues may have consumed the 24h window since.
        # Lock the products (id order, deadlock-free — mirrors the wizard's own
        # lock) and re-run the SAME cap core, so approving a held request can
        # never sneak an issue over the daily cap. Done before the re-plan so
        # the stock read below is serialised under the same lock too.
        locked_ids = sorted(p.id for p in by_product)
        if locked_ids:
            self.env.cr.execute(
                "SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                (tuple(locked_ids),),
            )
        self.env["wms.scan.issue"]._enforce_overuse_caps_for(by_product)

        replanned = []  # (product, [(quant, take), ...])
        for product, qty in by_product.items():
            plan, missing = StockLocation.find_oldest_quants_for_product(
                product.id,
                qty,
                parent_location_id=parent_location_id,
            )
            if missing or not plan:
                raise UserError(
                    "Stock for %s has moved since this request was made — "
                    "the warehouse can no longer cover the requested quantity "
                    "(%g, short by %g). Nothing was issued. Reject this request "
                    "and ask the keeper to scan it again against what's on the "
                    "shelf now." % (product.display_name, qty, missing)
                )
            replanned.append((product, plan))

        # Build the audit / picking vals from the frozen snapshot, then hand
        # off to the shared helper the inline Scan Issue path also uses. The
        # origin MUST start 'Barcode' so the audit-triplet DB CHECK +
        # @api.constrains still fire and enforce wms_storekeeper_id.
        origin = "Barcode FIFO issue (approved %s)" % (self.name or "")
        picking = self.env["wms.scan.issue"]._build_issue_picking(
            warehouse=self.warehouse_id,
            destination=self.destination_id,
            replanned=replanned,
            origin=origin,
            audit_vals={
                "wms_taken_by": (self.taken_by or "").strip(),
                "wms_ordered_by": (self.ordered_by or "").strip(),
                "wms_storekeeper_id": self.storekeeper_id.id,
                "wms_department_id": self.department_id.id,
                "wms_purpose_id": self.purpose_id.id or False,
                "wms_animal_id": self.animal_id.id or False,
                "wms_issued_for": self.department_id.legacy_issued_for or "other",
                "wms_expected_return_date": self.expected_return_date or False,
            },
            usage_note=self.usage_note,
        )

        self.write(
            {
                "picking_id": picking.id,
                "approver_id": self.env.user.id,
                "decision_date": fields.Datetime.now(),
                "state": "approved",
            }
        )

        # Carry the keeper's photo onto the delivery's audit trail.
        if self.photo:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": "issue-photo-%s.jpg" % picking.name,
                    "datas": self.photo,
                    "res_model": "stock.picking",
                    "res_id": picking.id,
                    "mimetype": "image/jpeg",
                }
            )
            picking.message_post(
                body="Operator photo attached at issue (carried from approval %s)."
                % (self.name or ""),
                attachment_ids=attachment.ids,
            )

        body = Markup(
            "<p><b>Approved.</b> Issued as delivery <b>%s</b> by <b>%s</b>.</p>"
            "<p>Value: <b>%g</b>; held for: %s. Keeper's reason:<br/>%s</p>"
        ) % (
            escape(picking.name or ""),
            escape(self.env.user.display_name or ""),
            self.issue_value,
            escape(self._held_reason_label()),
            escape(self.keeper_reason or "(none)"),
        )
        self.message_post(body=body, subject="Issue approved", message_type="notification")
        self._clear_manager_activity()
        return self.action_open_picking()

    def action_reject(self):
        """Reject the held issue: nothing is issued, state -> rejected, the
        reason recorded in the chatter."""
        self.ensure_one()
        self._ensure_can_decide()
        if self.state != "pending":
            raise UserError(
                "This request has already been %s — it can no longer be rejected."
                % dict(self._fields["state"].selection).get(self.state, self.state)
            )
        self.write(
            {
                "state": "rejected",
                "approver_id": self.env.user.id,
                "decision_date": fields.Datetime.now(),
            }
        )
        body = Markup(
            "<p><b>Rejected</b> by <b>%s</b>. Nothing was issued.</p>"
            "<p>Held for: %s. Keeper's reason:<br/>%s</p>"
        ) % (
            escape(self.env.user.display_name or ""),
            escape(self._held_reason_label()),
            escape(self.keeper_reason or "(none)"),
        )
        self.message_post(body=body, subject="Issue rejected", message_type="notification")
        self._clear_manager_activity()
        return True

    def _held_reason_label(self):
        self.ensure_one()
        reasons = []
        if self.reason_high_value:
            reasons.append("high value (%g)" % self.issue_value)
        if self.reason_min_life:
            reasons.append(
                "requested too soon (%s)" % (self.min_life_product_id.display_name or "product")
            )
        return "; ".join(reasons) or "(unspecified)"

    def notify_managers_held(self):
        """Ping every WMS Manager via Discuss that a request needs approval.

        Uses the mandatory ``notify_wms_managers`` helper (message_notify ->
        Discuss inbox + systray, plus email when wms_reports.alert_email=1).
        Imported lazily so wms_barcode does NOT need a manifest dependency on
        wms_reports (which sits in a higher layer and would invert the graph).
        Best-effort — a notification failure (or a not-yet-installed
        wms_reports) must never break the keeper's action, matching the
        helper's own best-effort contract."""
        self.ensure_one()
        try:
            from odoo.addons.wms_reports.models.wms_notify import notify_wms_managers
        except ImportError:  # wms_reports not installed — degrade quietly
            _logger.warning("wms notify: wms_reports unavailable, skipping held-issue alert")
            return
        body = Markup(
            "<p><b>An issue needs your approval.</b></p>"
            "<p>Request <b>%(name)s</b> — held for: %(reason)s.</p>"
            "<p>Value: <b>%(value)g</b>; department: <b>%(dept)s</b>; "
            "Store Keeper: <b>%(keeper)s</b>.</p>"
            "<p>Keeper's reason:<br/>%(kreason)s</p>"
            "<p>Open <i>WMS -> Approvals</i> to Approve or Reject.</p>"
        ) % {
            "name": escape(self.name or ""),
            "reason": escape(self._held_reason_label()),
            "value": self.issue_value,
            "dept": escape(self.department_id.name or "(none)"),
            "keeper": escape(self.storekeeper_id.name or "(unknown)"),
            "kreason": escape(self.keeper_reason or "(none)"),
        }
        notify_wms_managers(self.env, body, "WMS — Issue awaiting approval: %s" % (self.name or ""))
        self._schedule_manager_activity()

    def _schedule_manager_activity(self):
        """Raise a To-Do activity on every WMS Manager so the systray activity
        badge (red counter) flags held issues — far more reliable than a Discuss
        ping that's easy to miss on a shared screen. Cleared on approve/reject.

        Best-effort and idempotent: never breaks the keeper's action, and won't
        double-schedule on a re-notify (skips a manager who already has one)."""
        self.ensure_one()
        try:
            rec = self.sudo()
            group = rec.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
            todo = rec.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            if not group or not todo:
                return
            already = rec.activity_ids.filtered(lambda a: a.activity_type_id == todo).mapped(
                "user_id"
            )
            summary = "Approve / reject held issue %s" % (self.name or "")
            for user in group.all_user_ids:
                if user in already:
                    continue
                rec.activity_schedule(
                    "mail.mail_activity_data_todo", summary=summary, user_id=user.id
                )
        except Exception as exc:  # noqa: BLE001 — best-effort, never block the keeper
            _logger.warning("wms approval: could not schedule manager activity: %s", exc)

    def _clear_manager_activity(self):
        """Drop the held-issue To-Do activities once the request is decided so
        the managers' systray badge clears. Best-effort."""
        self.ensure_one()
        try:
            self.sudo().activity_unlink(["mail.mail_activity_data_todo"])
        except Exception as exc:  # noqa: BLE001
            _logger.warning("wms approval: could not clear manager activity: %s", exc)

    def action_open_picking(self):
        """Open the delivery this approval created. Public so the form's
        stat button can call it (Odoo 19 refuses to bind a private method
        to a button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
        }


class WmsIssueApprovalLine(models.Model):
    """A single planned deduction snapshotted from the Scan Issue plan.

    The ``quant_id`` may be stale by approval time (the planner re-plans
    against live stock on approve), so it is kept only for traceability —
    ``product_id`` + ``take`` are what get replayed."""

    _name = "wms.issue.approval.line"
    _description = "Planned line on a held Scan Issue"

    approval_id = fields.Many2one(
        "wms.issue.approval",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one("product.product", required=True)
    location_id = fields.Many2one("stock.location", string="Slot")
    quant_id = fields.Many2one(
        "stock.quant",
        help="The quant planned at request time. May be stale at approval "
        "time — the approval re-plans against live stock.",
    )
    take = fields.Float()
    expiry_date = fields.Date(string="Expires")

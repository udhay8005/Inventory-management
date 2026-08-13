"""Weekly inventory audit by Store Keepers.

Why
---
Cycle-count-due lists individual slots overdue for counting, but the
trust wants a structured *audit* the keeper performs end-to-end:
walk every slot, scan every product, record what's actually there,
flag variances, submit to the Admin. The Admin then reviews and
either accepts the counts (the system applies adjustments) or
challenges specific lines.

Workflow
--------
        draft  ->  in_progress  ->  submitted  ->  reviewed
        (Admin    (Store Keeper    (Auto: store    (Admin:
        creates   scans + counts)  keeper hits     'Accept' or
        + assigns                  'Submit',       'Reject and
        keeper)                    chatter pings   re-open')
                                   Admin)

Lines are auto-populated from current stock.quant rows at audit
creation time so the keeper sees the expected count next to a fresh
count column. Variances (counted - expected) compute on the fly and
the form colour-codes mismatches.
"""

from __future__ import annotations

from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WmsAudit(models.Model):
    _name = "wms.audit"
    _description = "Inventory audit run"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In progress"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
        required=True,
    )
    auditor_user_id = fields.Many2one(
        "res.users",
        string="Auditor",
        tracking=True,
        default=lambda self: self.env.user,
        domain="[('group_ids.id', '=?', group_wms_user_id)]",
        help="The Store Keeper doing the walk. Defaults to the user " "who opens the audit.",
    )
    storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="On-duty Store Keeper",
        tracking=True,
        help="Roster entry for the actual human running the audit. "
        "May differ from the Odoo login when the desk is shared.",
    )
    started_at = fields.Datetime(tracking=True, readonly=True)
    submitted_at = fields.Datetime(tracking=True, readonly=True)
    reviewed_at = fields.Datetime(tracking=True, readonly=True)
    reviewed_by = fields.Many2one(
        "res.users",
        string="Reviewed by",
        tracking=True,
        readonly=True,
    )
    line_ids = fields.One2many("wms.audit.line", "audit_id", string="Lines")
    note = fields.Text(string="Notes")

    line_count = fields.Integer(compute="_compute_counts")
    scope = fields.Selection(
        [
            ("recorded", "Stock on record"),
            ("full", "Full walk — every slot, empty ones included"),
        ],
        default="recorded",
        required=True,
        tracking=True,
        help="Stock on record: count what the books say is there (including "
        "any slot showing NEGATIVE stock, which needs looking at). "
        "Full walk: also list every empty slot in range, so goods that were "
        "never recorded — put away in the wrong slot, returned without a scan "
        "— can actually be found. A full walk takes longer; use the Area "
        "filter to do one zone at a time.",
    )
    zone_id = fields.Many2one(
        "stock.location",
        string="Area to count",
        domain="[('usage', '=', 'internal')]",
        help="Optional: count only this zone or rack. Leave empty for the "
        "whole warehouse. Counting one area a week is how a full walk stays "
        "practical.",
    )
    found_count = fields.Integer(
        string="Unrecorded finds",
        compute="_compute_counts",
        store=False,
        help="Lines for stock the books did not know about at all.",
    )
    variance_count = fields.Integer(
        string="Variances",
        compute="_compute_counts",
        store=False,
        help="Lines where counted_qty != expected_qty.",
    )

    # Group_id helper for the domain on auditor_user_id - tells the
    # client which group counts as "store keeper" so the dropdown
    # filters correctly.
    group_wms_user_id = fields.Integer(compute="_compute_group_id")

    @api.depends(
        "line_ids",
        "line_ids.counted_qty",
        "line_ids.expected_qty",
        "line_ids.is_found_line",
    )
    def _compute_counts(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.variance_count = sum(1 for ln in rec.line_ids if ln.counted_qty != ln.expected_qty)
            # Stock nobody had on the books: either a line the keeper added for
            # a surprise find, or an empty slot on a full walk that turned out
            # to hold something. Worth its own number — it is the one figure a
            # count sheet built from the books could never produce.
            rec.found_count = sum(
                1
                for ln in rec.line_ids
                if ln.counted_qty > 0 and not ln.expected_qty and ln.product_id
            )

    @api.depends()
    def _compute_group_id(self):
        grp = self.env.ref("wms_location.group_wms_user", raise_if_not_found=False)
        for rec in self:
            rec.group_wms_user_id = grp.id if grp else 0

    # ---------------------------------------------------------------
    # Create: stamp sequence name
    # ---------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.audit") or "AUDIT/NEW"
        return super().create(vals_list)

    # ---------------------------------------------------------------
    # Workflow transitions
    # ---------------------------------------------------------------
    def action_start(self):
        """Move to in_progress + auto-populate lines from current
        quants if line_ids is empty.
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Audit %s is not in draft. Open a fresh audit to " "re-walk the warehouse.")
                    % rec.name
                )
            if not rec.line_ids:
                rec._populate_from_quants()
            rec.state = "in_progress"
            rec.started_at = fields.Datetime.now()
            rec.message_post(
                body=Markup(
                    "<p><b>Audit started.</b> %d slot/product combinations "
                    "queued. Walk the racks and enter the counted "
                    "quantity for each line.</p>"
                )
                % len(rec.line_ids),
                subject="Audit started",
            )

    def _populate_from_quants(self):
        """Build the count sheet the keeper walks with.

        Counts only the warehouse storage tree (each warehouse's lot-stock and
        its children: zones / racks / compartments / slots / floor). Excludes
        the top-level "Trust internal use" sink (already-consumed goods) and
        the Damage / Repair internal locations - none of which are shelf stock
        the keeper physically walks - using the same lot_stock_id child_of
        guard the Stock-Value report applies. Without this, every batch ever
        issued to the sink showed up as an expected line to find, generating
        bogus negative variances and bloating the count list over months.

        UAT R4 — what this used to MISS, and why it mattered:

        * ``quantity > 0`` hid NEGATIVE stock. A slot driven to -2 by an
          over-issue never appeared on any count sheet, so the keeper was
          never asked to look at it and the error sat in the books forever.
          The filter is now ``!= 0``: a negative line shows expected -2, the
          keeper counts what is really there, and accepting the audit corrects
          it.
        * a slot the books call EMPTY was never walked, so stock that was
          never recorded — put away in the wrong slot, returned without a
          scan, delivered straight to a shelf — could not be discovered by
          counting. It is invisible to the books BECAUSE it is unrecorded, and
          the count sheet was built from the books. Choosing the "Full walk"
          scope now lists every slot in range, empty ones included, so the
          keeper can write down what is actually there.
        """
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        Loc = self.env["stock.location"].sudo()
        storage = self.env["stock.warehouse"].search([]).lot_stock_id
        if not storage:
            return
        # A zone/rack filter keeps a full walk practical: "Main Store this
        # week, Godown next week" instead of one impossible 200-slot sweep.
        roots = self.zone_id or storage
        Line = self.env["wms.audit.line"].sudo()
        vals_list = []
        covered = set()
        for q in Quant.search([("location_id", "child_of", roots.ids), ("quantity", "!=", 0)]):
            vals_list.append(
                {
                    "audit_id": self.id,
                    "location_id": q.location_id.id,
                    "product_id": q.product_id.id,
                    "expected_qty": q.quantity,
                    "counted_qty": 0.0,
                    "is_found_line": False,
                }
            )
            covered.add(q.location_id.id)
        if self.scope == "full":
            empty_slots = Loc.search(
                [
                    ("id", "child_of", roots.ids),
                    ("usage", "=", "internal"),
                    ("wms_location_type", "in", ("slot", "floor")),
                    ("id", "not in", list(covered)),
                ]
            )
            for loc in empty_slots:
                # No product: the books say nothing is here. The keeper fills
                # in what they find, or leaves it at zero to record "walked,
                # confirmed empty" — which is itself worth having.
                vals_list.append(
                    {
                        "audit_id": self.id,
                        "location_id": loc.id,
                        "expected_qty": 0.0,
                        "counted_qty": 0.0,
                        "is_found_line": False,
                    }
                )
        Line.create(vals_list)

    def action_submit(self):
        """Store keeper hands the audit in. Lock the lines and post a
        digest message to every WMS Manager so they see it in their
        Inbox the next time Odoo opens."""
        for rec in self:
            if rec.state != "in_progress":
                raise UserError(
                    _("Only an in-progress audit can be submitted. Audit " "%s is currently in %s.")
                    % (rec.name, rec.state)
                )
            if not rec.storekeeper_id:
                raise UserError(
                    _(
                        "Pick the on-duty Store Keeper from the roster "
                        "before submitting (drop-down at the top of the "
                        "form)."
                    )
                )
            counted = rec.line_ids.filtered("is_counted")
            if rec.line_ids and not counted:
                raise UserError(
                    _(
                        "Nothing on this sheet has been counted yet, so there is "
                        "nothing to submit. Walk the slots and enter what you "
                        "find - a slot you checked and found empty counts: enter 0."
                    )
                )
            uncounted = len(rec.line_ids) - len(counted)

            # Single write so the keeper's in_progress -> submitted transition
            # clears the finalised-state write guard in one shot (the guard
            # reads the pre-write state, still in_progress here). A second
            # attribute assignment would be evaluated against the now-submitted
            # state and blocked.
            rec.write({"state": "submitted", "submitted_at": fields.Datetime.now()})

            # Headline numbers
            v = rec.variance_count
            # Build the digest body. Markup() so the HTML renders
            # instead of escaping.
            top_variances = rec.line_ids.filtered(
                lambda ln: ln.counted_qty != ln.expected_qty
            ).sorted(lambda ln: abs(ln.counted_qty - ln.expected_qty), reverse=True)[:10]
            rows = []
            for line in top_variances:
                colour = "#cc0000" if line.counted_qty < line.expected_qty else "#0066aa"
                rows.append(
                    "<tr><td style='padding:2px 8px'>%s</td>"
                    "<td style='padding:2px 8px'>%s</td>"
                    "<td style='padding:2px 8px;text-align:right'>%g</td>"
                    "<td style='padding:2px 8px;text-align:right'>%g</td>"
                    "<td style='padding:2px 8px;text-align:right;color:%s'>"
                    "<b>%+g</b></td></tr>"
                    % (
                        line.location_id.complete_name or "",
                        line.product_id.display_name,
                        line.expected_qty,
                        line.counted_qty,
                        colour,
                        line.counted_qty - line.expected_qty,
                    )
                )
            # Say it in the digest, because this is the manager's decision
            # point: accepting adjusts only what was counted, and the slots
            # nobody reached are still unverified. Silence here is how a
            # half-walked sheet gets treated as a full physical count.
            partial_note = Markup("")
            if uncounted:
                partial_note = Markup(
                    "<p style='color:#b45309'><b>%d of %d slot(s) were not "
                    "counted</b> and are not part of this count. Accepting "
                    "adjusts only the %d counted line(s); the rest keep their "
                    "current stock and remain unverified.</p>"
                ) % (uncounted, len(rec.line_ids), len(counted))

            digest = Markup(
                "<p><b>Audit submitted: %s.</b></p>"
                "<p>%d line(s) counted; <b>%d variance(s)</b>. "
                "Top mismatches:</p>"
                "<table style='border-collapse:collapse;font-family:Arial'>"
                "<tr><th style='text-align:left;padding:2px 8px'>Slot</th>"
                "<th style='text-align:left;padding:2px 8px'>Product</th>"
                "<th style='text-align:right;padding:2px 8px'>Expected</th>"
                "<th style='text-align:right;padding:2px 8px'>Counted</th>"
                "<th style='text-align:right;padding:2px 8px'>Δ</th></tr>"
                "%s</table>"
                "%s"
                "<p><i>Open the audit to review and accept the counts.</i></p>"
            ) % (rec.name, len(counted), v, "".join(rows), partial_note)

            rec.message_post(
                body=digest,
                subject="Audit submitted: %s" % rec.name,
                message_type="notification",
            )
            # Also notify the WMS Manager group via partner_ids so the
            # message shows in their Inbox.
            mgr = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
            if mgr:
                rec.message_subscribe(partner_ids=mgr.all_user_ids.partner_id.ids)

    # States in which a keeper may no longer edit the audit - only a Manager
    # can change a finalised audit (re-open / correct). This is the record-level
    # second line of defense behind the in-method manager re-check on accept.
    _KEEPER_LOCKED_STATES = ("submitted", "reviewed", "rejected")
    # Chatter / activity system fields a keeper may still write on a locked
    # audit (action_submit posts a digest right after the transition); only
    # BUSINESS fields are frozen once submitted.
    _MAIL_SYSTEM_FIELDS = frozenset(
        {
            "message_ids",
            "message_follower_ids",
            "message_partner_ids",
            "message_main_attachment_id",
            "message_is_follower",
            "activity_ids",
        }
    )

    def write(self, vals):
        """Freeze a finalised audit against keeper edits (record-level guard).

        A keeper holds write on wms.audit (they author/submit audits), so once
        an audit is submitted/reviewed/rejected they could otherwise still edit
        it over RPC - e.g. change counts after submitting but before the manager
        reviews. Managers (and superuser internal paths) bypass; chatter writes
        are allowed so action_submit's own digest post still works.
        """
        if (
            not self.env.su
            and set(vals) - self._MAIL_SYSTEM_FIELDS
            and not self.env.user.has_group("wms_location.group_wms_manager")
        ):
            for rec in self:
                if rec.state in self._KEEPER_LOCKED_STATES:
                    raise AccessError(
                        _(
                            "Audit %s is already %s — only a Manager can change "
                            "it. Ask a Manager to re-open it if a correction is "
                            "needed."
                        )
                        % (rec.name, rec.state)
                    )
        return super().write(vals)

    def _ensure_manager(self):
        """Defense-in-depth manager re-check for the audit decision methods.

        The Accept / Reject buttons are hidden in the form for non-managers,
        but the keeper holds write+create on ``wms.audit`` (they author and
        submit audits), so a forced RPC / dev-mode call could otherwise reach
        these methods and let a keeper self-accept their own count — silently
        overwriting live stock and defeating the manager-review gate the audit
        workflow exists to enforce. Mirrors
        ``wms.issue.approval._ensure_can_decide``.
        """
        self.ensure_one()
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise AccessError(
                _(
                    "Only a WMS Manager can accept or reject an inventory "
                    "audit. Submit it and ask a Manager to review."
                )
            )

    def action_review_accept(self):
        """Admin accepts the audit. Variances become stock adjustments
        so the books match the physical count."""
        for rec in self:
            rec._ensure_manager()
            # FPAT Critical: serialise concurrent Accepts on the same audit so
            # a double-click / parallel-RPC cannot apply the variance delta
            # twice. Lock the audit row FIRST and re-check state from the DB
            # (a fresh read inside the lock) - the previous in-Python check
            # raced because two clients each saw state='submitted' and both
            # proceeded to write deltas. Flush any pending in-ORM writes so
            # the SELECT-FOR-UPDATE locks against current state, not stale.
            rec.flush_recordset(["state"])
            self.env.cr.execute("SELECT state FROM wms_audit WHERE id = %s FOR UPDATE", (rec.id,))
            row = self.env.cr.fetchone()
            db_state = row[0] if row else None
            if db_state != "submitted":
                raise UserError(
                    _("Only a submitted audit can be reviewed. %s is in %s.")
                    % (rec.name, db_state or "?")
                )
            rec.state = "reviewed"
            rec.reviewed_at = fields.Datetime.now()
            rec.reviewed_by = self.env.user

            # Apply variances as stock inventory adjustments. HIGH fix: lock
            # the audited products so a concurrent Scan Issue / Receipt cannot
            # race this adjustment, and apply the audit's DELTA
            # (counted - expected, measured at count time) to the CURRENT live
            # quantity - NOT a blind overwrite to counted_qty. A blind
            # overwrite would silently erase any issue/receipt that legitimately
            # happened during the (possibly multi-day) audit window.
            # A product-less line is a full-walk slot the keeper confirmed
            # empty: there is nothing to book, and no product to lock.
            # is_counted is the load-bearing term. Without it, every slot the
            # keeper never reached is a line reading counted=0 against
            # expected=N, and accepting the audit applies delta -N to each -
            # wiping the stock of every unvisited slot, silently, because the
            # digest only lists the ten largest variances. Harmless while an
            # audit was 2 lines; a disaster the moment "Full walk" makes it 225.
            variance_lines = rec.line_ids.filtered(
                lambda ln: ln.is_counted and ln.product_id and ln.counted_qty != ln.expected_qty
            )
            prod_ids = sorted(set(variance_lines.mapped("product_id").ids))
            if prod_ids:
                self.env.cr.execute(
                    "SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                    (tuple(prod_ids),),
                )
            Quant = self.env["stock.quant"].sudo()
            for line in variance_lines:
                quant = Quant.search(
                    [
                        ("product_id", "=", line.product_id.id),
                        ("location_id", "=", line.location_id.id),
                    ],
                    limit=1,
                )
                delta = line.counted_qty - line.expected_qty
                if quant:
                    quant.with_context(inventory_mode=True).write(
                        {"quantity": quant.quantity + delta}
                    )
                elif delta > 0:
                    # No live quant: create at the DELTA, not the raw count. If
                    # an issue legitimately emptied the slot during the audit
                    # window, re-creating it at counted_qty would undo that
                    # issue; the delta (counted - expected) preserves it.
                    Quant.with_context(inventory_mode=True).create(
                        {
                            "product_id": line.product_id.id,
                            "location_id": line.location_id.id,
                            "quantity": delta,
                        }
                    )

            rec.message_post(
                body=Markup(
                    "<p><b>Audit accepted</b> by <b>%s</b>. "
                    "%d adjustment(s) applied; quants now match the "
                    "physical count.</p>"
                )
                % (self.env.user.display_name, rec.variance_count),
                subject="Audit reviewed",
            )

    def action_reject(self):
        for rec in self:
            rec._ensure_manager()
            if rec.state != "submitted":
                raise UserError(_("Only a submitted audit can be rejected."))
            rec.state = "rejected"
            rec.message_post(
                body=Markup(
                    "<p><b>Audit rejected</b> by <b>%s</b>. The Store "
                    "Keeper should re-walk the flagged lines and "
                    "re-submit a fresh audit.</p>"
                )
                % self.env.user.display_name,
                subject="Audit rejected",
            )


class WmsAuditLine(models.Model):
    _name = "wms.audit.line"
    _description = "One slot+product row in an audit"
    _order = "location_id, product_id"

    audit_id = fields.Many2one(
        "wms.audit",
        required=True,
        ondelete="cascade",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Slot",
        required=True,
        domain="[('usage', '=', 'internal')]",
        ondelete="restrict",
    )
    product_id = fields.Many2one(
        "product.product",
        # Optional on purpose. A full walk lists EMPTY slots, where the whole
        # point is that the books do not know what (if anything) is there —
        # the keeper names it if they find something. A required field here is
        # what made unrecorded stock impossible to write down.
        help="What is in this slot. Left empty on a full-walk line until the "
        "keeper finds something there.",
    )
    is_found_line = fields.Boolean(
        string="Added by keeper",
        default=True,
        help="True for a line the keeper added while walking — stock the books "
        "did not list. Generated lines are False and keep their slot and "
        "product locked so a count cannot be pointed at the wrong shelf.",
    )
    expected_qty = fields.Float(
        string="Expected",
        readonly=True,
        help="Quantity Odoo's books show in this slot at audit start.",
    )
    counted_qty = fields.Float(
        string="Counted",
        help="What the Store Keeper actually saw on the shelf.",
    )
    is_counted = fields.Boolean(
        string="Counted?",
        default=False,
        help="Ticked once someone has actually stood in front of this slot. "
        "A blank line is NOT the same as a slot counted at zero, and the "
        "difference decides whether accepting the audit touches this stock.",
    )
    _counted_qty_nonneg = models.Constraint(
        "CHECK(counted_qty >= 0)",
        "Counted quantity cannot be negative.",
    )
    variance = fields.Float(
        compute="_compute_variance",
        store=True,
        readonly=True,
        help="counted - expected. Negative = missing stock, " "positive = unexpected stock found.",
    )
    note = fields.Char(
        string="Note",
        help="Optional comment: 'wrong slot', 'damaged units left "
        "in place', 'expired - moved to trash', etc.",
    )
    scan_confirm = fields.Char(
        string="Scan to confirm",
        help="Optional: scan the product's barcode while counting this line. "
        "The Scan column turns green when it matches this line's product — a "
        "cheap guard against counting the wrong look-alike item.",
    )
    scan_status = fields.Selection(
        [
            ("blank", "Not scanned"),
            ("match", "Confirmed"),
            ("mismatch", "Wrong item!"),
        ],
        string="Scan",
        compute="_compute_scan_status",
        help="Confirmed = the scanned barcode matches this line's product; "
        "Wrong item = it doesn't (or is unknown). Advisory — never blocks.",
    )
    state = fields.Selection(
        related="audit_id.state",
        store=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # A line the keeper types in by hand (a surprise find) arrives with
            # a count already on it and is counted by definition. A generated
            # sheet line arrives at 0.0 and is NOT.
            if "is_counted" not in vals and vals.get("counted_qty"):
                vals["is_counted"] = True
        return super().create(vals_list)

    @api.constrains("product_id", "counted_qty")
    def _check_counted_line_names_a_product(self):
        """You cannot count "3 of something". A full-walk line may sit at zero
        with no product (walked, confirmed empty), but the moment a quantity
        is entered the keeper has to say WHAT it is, or the accept step has
        nothing to book the stock against."""
        for line in self:
            if line.counted_qty and not line.product_id:
                raise ValidationError(
                    _(
                        "You recorded %(qty)g in %(loc)s but did not say what it "
                        "is. Pick the product on that line — a count needs to "
                        "name the item, or it cannot be booked into stock."
                    )
                    % {"qty": line.counted_qty, "loc": line.location_id.display_name}
                )

    @api.depends("counted_qty", "expected_qty")
    def _compute_variance(self):
        for line in self:
            line.variance = line.counted_qty - line.expected_qty

    @api.depends("scan_confirm", "product_id")
    def _compute_scan_status(self):
        """Resolve the scanned code against THIS line's product. Matches the
        product barcode / SKU directly, and (when wms_barcode is installed —
        no hard dependency) a carton/alias code via its resolver. Never raises:
        an error resolving a stray scan must not break the count."""
        for line in self:
            code = (line.scan_confirm or "").strip()
            if not code:
                line.scan_status = "blank"
                continue
            prod = line.product_id
            if not prod:
                # A full-walk line with nothing named yet: a scan here is
                # the keeper telling us what they just found, not a
                # confirmation of something already on the sheet.
                line.scan_status = "blank"
                continue
            hit = code in (prod.barcode or "", prod.default_code or "")
            if not hit and "wms.barcode.alias" in line.env:
                try:
                    info = line.env["wms.barcode.alias"].resolve(code)
                    hit = bool(info.get("product")) and info["product"].id == prod.id
                except Exception:  # noqa: BLE001
                    hit = False
            line.scan_status = "match" if hit else "mismatch"

    def write(self, vals):
        """Freeze line counts once the parent audit is finalised.

        Keepers enter counts while the audit is draft / in_progress; once it is
        submitted (or reviewed / rejected) the counts ARE the record of what was
        physically found, so a keeper must not be able to revise them over RPC
        after handing the audit in. Managers (and superuser internal paths)
        bypass; to change a submitted count, a manager rejects the audit and the
        keeper re-walks it. Mirrors the absolute unlink() guard below.

        Also marks the line as counted: writing a figure into the Counted
        column IS the act of counting. That is what separates "I walked to that
        slot and it held nothing" from "nobody got that far" - two states
        previously stored identically as 0.0, the second of which silently
        zeroed real stock when the manager accepted the audit.
        """
        if "counted_qty" in vals and "is_counted" not in vals:
            vals = dict(vals, is_counted=True)
        if not self.env.su and not self.env.user.has_group("wms_location.group_wms_manager"):
            for line in self:
                if line.audit_id.state in ("submitted", "reviewed", "rejected"):
                    raise AccessError(
                        _(
                            "This audit has been submitted — its counts are "
                            "locked. Ask a Manager to reject it so the count can "
                            "be re-walked."
                        )
                    )
        return super().write(vals)

    def unlink(self):
        """Block deletion of audit lines once the parent audit has left
        'draft'. Lines are auto-populated at creation and ARE the count of
        record; deleting them after submission would let a Store Keeper
        (or any RPC caller) silently rewrite audit history. Defence-in-depth
        on top of perm_unlink=0 for group_wms_user in ir.model.access.csv —
        this ORM guard also fires on sudo() and manager paths. If a line is
        wrong, the Admin rejects the audit and the keeper re-walks it.
        """
        locked = self.filtered(lambda ln: ln.audit_id.state not in ("draft", False))
        if locked:
            # Intentional ORM-level delete guard: raising in unlink() (rather
            # than via @api.ondelete) is deliberate so it also fires on sudo()
            # and manager unlink paths and mirrors perm_unlink=0. See docstring.
            # pylint: disable=no-raise-unlink
            raise UserError(
                _(
                    "Cannot delete audit line(s) on a submitted or reviewed "
                    "audit — the count of record is immutable once submitted. "
                    "Reject the audit instead and have the Store Keeper "
                    "re-walk it (a fresh audit is created)."
                )
            )
        return super().unlink()

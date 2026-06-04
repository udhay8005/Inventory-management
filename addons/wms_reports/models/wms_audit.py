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
from odoo.exceptions import UserError


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

    @api.depends("line_ids", "line_ids.counted_qty", "line_ids.expected_qty")
    def _compute_counts(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.variance_count = sum(1 for ln in rec.line_ids if ln.counted_qty != ln.expected_qty)

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
        """Snapshot every internal quant > 0 into audit lines so the
        keeper has the expected value to compare against."""
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        quants = Quant.search(
            [
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]
        )
        Line = self.env["wms.audit.line"].sudo()
        for q in quants:
            Line.create(
                {
                    "audit_id": self.id,
                    "location_id": q.location_id.id,
                    "product_id": q.product_id.id,
                    "expected_qty": q.quantity,
                    "counted_qty": 0.0,
                }
            )

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
            rec.state = "submitted"
            rec.submitted_at = fields.Datetime.now()

            # Headline numbers
            n = len(rec.line_ids)
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
                "<p><i>Open the audit to review and accept the counts.</i></p>"
            ) % (rec.name, n, v, "".join(rows))

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

    def action_review_accept(self):
        """Admin accepts the audit. Variances become stock adjustments
        so the books match the physical count."""
        for rec in self:
            if rec.state != "submitted":
                raise UserError(
                    _("Only a submitted audit can be reviewed. %s is in " "%s.")
                    % (rec.name, rec.state)
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
            variance_lines = rec.line_ids.filtered(lambda ln: ln.counted_qty != ln.expected_qty)
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
                elif line.counted_qty > 0:
                    Quant.with_context(inventory_mode=True).create(
                        {
                            "product_id": line.product_id.id,
                            "location_id": line.location_id.id,
                            "quantity": line.counted_qty,
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
        required=True,
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
    state = fields.Selection(
        related="audit_id.state",
        store=False,
    )

    @api.depends("counted_qty", "expected_qty")
    def _compute_variance(self):
        for line in self:
            line.variance = line.counted_qty - line.expected_qty

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
            raise UserError(
                _(
                    "Cannot delete audit line(s) on a submitted or reviewed "
                    "audit — the count of record is immutable once submitted. "
                    "Reject the audit instead and have the Store Keeper "
                    "re-walk it (a fresh audit is created)."
                )
            )
        return super().unlink()

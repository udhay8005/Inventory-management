from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Structured "what was this issued for" categories. The trust runs several
# distinct cost centres off one store; a structured field (vs only the
# free-text usage note) lets the Consumption Value report answer "how much
# did Cows consume vs Pooja vs Maintenance" without parsing prose.
WMS_ISSUED_FOR_SELECTION = [
    ("cows", "Cows / Gaushala"),
    ("pooja", "Pooja / Temple"),
    ("maintenance", "Maintenance / Repairs"),
    ("project", "Project / Construction"),
    ("administration", "Administration / Office"),
    ("other", "Other"),
]


class StockPicking(models.Model):
    """Audit trail fields populated by the Scan Issue wizard.

    Trust workflow:
      • The Store Keeper roster (wms.storekeeper) holds the names of
        the actual humans who rotate on the store desk. They typically
        share one Odoo login, so the on-duty name is picked from the
        roster each time — not auto-detected from env.user.
      • Taken by — the person physically receiving the items. Plain
        text because not every taker has a system record.
      • Ordered by — whoever authorised the issue (the cow-care lead,
        the Manager, etc.). Plain text for the same reason.

    These fields stay editable after validate so an Admin can fix a
    typo without re-issuing the stock move. They're shown on the
    picking's form view by an inherited view defined in
    `views/stock_picking_views.xml`.
    """

    _inherit = ["stock.picking", "wms.keeper.warning.mixin"]

    wms_taken_by = fields.Char(
        string="Handled by",
        index=True,
        tracking=True,
        help="Name of the person who physically handled this stock at the "
        "warehouse door — the receiver on an incoming delivery, or the "
        "person who took the goods on an issue. Neutral so the same "
        "column reads naturally on both directions of the transfer.",
    )
    wms_ordered_by = fields.Char(
        string="Ordered by",
        index=True,
        tracking=True,
        help="Name of the person who authorised this issue "
        "(the Manager / cow-care lead / project owner).",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        tracking=True,
        help="The actual human Store Keeper running the desk at the time of "
        "this issue. Picked from the roster the Admin maintains under "
        "Configuration → Store Keepers.",
    )
    wms_issued_for = fields.Selection(
        WMS_ISSUED_FOR_SELECTION,
        string="Issued for",
        index=True,
        tracking=True,
        help="Which part of the trust consumed this stock. Set by the Scan "
        "Issue wizard so the Consumption Value report can break spend down by "
        "purpose (Cows, Pooja, Maintenance, ...). Kept for backward "
        "compatibility and derived from the department on new issues; the "
        "structured Department field below is now the primary capture.",
    )
    # ---- Issue dimensions (F1) -------------------------------------------
    # Structured Department / Purpose / Animal captured by the Scan Issue
    # wizard. Department supersedes the legacy wms_issued_for selection as
    # the primary "what was this consumed for" dimension (the consumption
    # report now breaks down by Department); wms_issued_for above is still
    # derived from the department so old reports/searches keep working.
    wms_department_id = fields.Many2one(
        "wms.department",
        string="Department",
        index=True,
        tracking=True,
        help="Which department / cost centre consumed this stock (Gaushala, "
        "Veterinary, Dairy, ...). Set by the Scan Issue wizard so the "
        "Consumption Value report can break spend down by department.",
    )
    wms_purpose_id = fields.Many2one(
        "wms.purpose",
        string="Purpose / reason",
        index=True,
        tracking=True,
        help="The structured reason this stock was issued (routine feed, "
        "treatment, repair, ...). Optional.",
    )
    wms_animal_id = fields.Many2one(
        "wms.animal",
        string="Animal / cow",
        index=True,
        tracking=True,
        help="The specific animal this issue was for, when it applies "
        "(e.g. a treatment for a named cow). Optional.",
    )
    wms_is_scan_issue = fields.Boolean(
        string="Scan Issue picking",
        default=False,
        copy=False,
        readonly=True,
        index=True,
        help="Internal: set True by the Scan Issue wizard on the picking it "
        "creates. The 24h daily-cap counter filters on this immutable flag "
        "instead of matching the free-text origin string ('Barcode FIFO%'), "
        "which any edit or collision could silently break.",
    )
    wms_audit_legacy = fields.Boolean(
        default=False,
        copy=False,
        readonly=True,
        index=False,
        help="Internal: set True by the 19.0.1.7.0 migration on pre-existing "
        "WMS-originated pickings that pre-date the audit-trail CHECK "
        "constraint. Allows the CHECK to grandfather historical rows "
        "while enforcing the invariant on every new row. Admin-readable "
        "filter target: search for wms_audit_legacy=True to review.",
    )

    # ---- Undo window (Batch 4) -------------------------------------------
    # A storekeeper who issues the wrong item / quantity can reverse it with
    # ONE click for a short window, WITHOUT deleting anything: the undo posts
    # a compensating internal transfer that puts the stock back. The window
    # is the System Parameter `wms_reports.undo_minutes` (default 15; 0 = off).
    wms_is_undo = fields.Boolean(
        string="Undo transfer",
        default=False,
        copy=False,
        readonly=True,
        index=True,
        help="Internal: True on the compensating transfer created by the Undo "
        "button. Such a transfer is itself never undoable.",
    )
    wms_reversed_by_id = fields.Many2one(
        "stock.picking",
        string="Undone by",
        copy=False,
        readonly=True,
        index=True,
        help="Set on the original picking once it has been undone — points at "
        "the compensating transfer. Its presence blocks a second undo.",
    )
    wms_undo_available = fields.Boolean(
        string="Can undo",
        compute="_compute_wms_undo_available",
        help="True only while this WMS transfer can still be safely reversed: "
        "it is done, both endpoints are internal, it has not already been "
        "undone, and it is inside the undo window.",
    )

    @api.depends(
        "state",
        "date_done",
        "wms_reversed_by_id",
        "wms_is_undo",
        "origin",
        "move_line_ids.quantity",
        "move_line_ids.location_id",
        "move_line_ids.location_dest_id",
    )
    def _compute_wms_undo_available(self):
        try:
            minutes = int(
                self.env["ir.config_parameter"].sudo().get_param("wms_reports.undo_minutes", "15")
                or 15
            )
        except (TypeError, ValueError):
            minutes = 15
        now = fields.Datetime.now()
        for p in self:
            ok = False
            if (
                minutes > 0
                and p.state == "done"
                and p.date_done
                and not p.wms_reversed_by_id
                and not p.wms_is_undo
                and (p.origin or "").startswith("Barcode")
            ):
                within = (now - p.date_done).total_seconds() <= minutes * 60
                lines = p.move_line_ids.filtered(lambda ml: ml.quantity)
                internal_only = bool(lines) and all(
                    ml.location_id.usage == "internal" and ml.location_dest_id.usage == "internal"
                    for ml in lines
                )
                ok = bool(within and internal_only)
            p.wms_undo_available = ok

    def action_wms_undo(self):
        """Reverse this WMS transfer with a compensating internal move.

        Nothing is deleted or edited: a brand-new transfer moves the stock
        from where it ended up back to where it came from. Safety rails:
          * a row lock on this picking serialises concurrent undo clicks,
          * we re-check `wms_undo_available` after locking (window / state),
          * the reverse must fully reserve or the whole thing aborts (the
            stock may have moved on) — never forcing a phantom move,
          * `wms_reversed_by_id` is set so a second undo is impossible.
        """
        self.ensure_one()
        # Serialise concurrent undo attempts on this exact picking.
        self.env.cr.execute("SELECT id FROM stock_picking WHERE id = %s FOR UPDATE", (self.id,))
        if not self.wms_undo_available:
            raise UserError(
                _(
                    "This transfer can no longer be undone. It may have already "
                    "been undone, the stock may have moved on, or the undo time "
                    "window has passed. Nothing was changed."
                )
            )
        lines = self.move_line_ids.filtered(lambda ml: ml.quantity)
        # Lock the products so a concurrent Scan Issue can't race the reversal.
        product_ids = sorted(set(lines.mapped("product_id").ids))
        if product_ids:
            self.env.cr.execute(
                "SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                (tuple(product_ids),),
            )
        warehouse = self.picking_type_id.warehouse_id
        ptype = warehouse.int_type_id if warehouse else self.picking_type_id
        reverse = self.env["stock.picking"].create(
            {
                "picking_type_id": ptype.id,
                "location_id": self.location_dest_id.id,
                "location_dest_id": self.location_id.id,
                # NOT 'Barcode...' so the audit-triplet CHECK doesn't require a
                # storekeeper; we copy the original's keeper anyway for the trail.
                "origin": "Undo: %s" % (self.name or ""),
                "wms_is_undo": True,
                "wms_storekeeper_id": self.wms_storekeeper_id.id,
            }
        )
        for ml in lines:
            self.env["stock.move"].create(
                {
                    "description_picking": "Undo %s" % (ml.product_id.display_name),
                    "product_id": ml.product_id.id,
                    "product_uom_qty": ml.quantity,
                    "product_uom": ml.product_uom_id.id,
                    "picking_id": reverse.id,
                    # Reverse direction: from where it ended up, back to source.
                    "location_id": ml.location_dest_id.id,
                    "location_dest_id": ml.location_id.id,
                }
            )
        reverse.action_confirm()
        reverse.action_assign()
        if reverse.move_ids.filtered(lambda m: m.state != "assigned"):
            raise UserError(
                _(
                    "Cannot undo: the stock is no longer where it was put, so it "
                    "cannot be moved back (it may have been issued again). Nothing "
                    "was changed."
                )
            )
        for ml in reverse.move_ids.move_line_ids:
            if not ml.quantity:
                ml.quantity = ml.quantity_product_uom or ml.move_id.product_uom_qty
        reverse.button_validate()
        self.wms_reversed_by_id = reverse.id
        self.message_post(
            body=Markup("<p><b>Undone.</b> Reversed by transfer <b>%s</b>.</p>")
            % (reverse.name or ""),
            subject="Undo",
            message_type="notification",
        )
        reverse.message_post(
            body=Markup("<p><b>Undo</b> of transfer <b>%s</b> — stock moved back.</p>")
            % (self.name or ""),
            subject="Undo",
            message_type="notification",
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": reverse.id,
            "view_mode": "form",
        }

    # Declarative DB constraint (Odoo 19 idiom — the old list-of-tuples
    # `_sql_constraints` is silently ignored on inherited models in 19).
    # The CHECK string is applied directly as a DDL fragment (NOT through
    # psycopg2 %-formatting), so the LIKE wildcard is a single '%'.
    _wms_audit_triplet_on_done = models.Constraint(
        # COALESCE on wms_audit_legacy is essential: a raw SQL INSERT that
        # omits the column leaves it NULL (Odoo applies default=False only
        # via the ORM, not at the DB level). Without COALESCE the whole OR
        # evaluates to NULL when legacy is NULL + storekeeper is NULL, and
        # PostgreSQL PASSES a CHECK that is NULL — silently defeating the
        # SQL-bypass protection. COALESCE(..., FALSE) forces that operand
        # to FALSE so the OR resolves to FALSE and the CHECK fires.
        "CHECK ("
        "state != 'done' "
        "OR origin IS NULL "
        "OR origin NOT LIKE 'Barcode%' "
        "OR wms_storekeeper_id IS NOT NULL "
        "OR COALESCE(wms_audit_legacy, FALSE) = TRUE"
        ")",
        "WMS-originated pickings must record the storekeeper before being marked done.",
    )

    # FPAT High: wms_is_scan_issue gates the daily-cap counter and the
    # Consumption Value report; clearing it on a done WMS picking silently
    # rewrites consumption history. Block the flip at the ORM layer. A
    # broader DB-CHECK was considered but rejected: not every done
    # Barcode-origin picking is a Scan Issue (damage/repair moves can carry
    # the same origin prefix), and a CHECK cannot tell intent. The write
    # override targets exactly the dangerous mutation - flipping TRUE -> FALSE
    # on a done Scan Issue picking.
    def write(self, vals):
        # Refuse to clear wms_is_scan_issue on a done WMS picking via the
        # ORM as well. The CHECK above is the ultimate backstop; this gives
        # operators a friendly error through the normal admin form.
        if "wms_is_scan_issue" in vals and vals.get("wms_is_scan_issue") is False:
            for rec in self:
                if (
                    rec.state == "done"
                    and rec.wms_is_scan_issue
                    and (rec.origin or "").startswith("Barcode")
                    and not rec.wms_audit_legacy
                ):
                    raise ValidationError(
                        _(
                            "Cannot clear the Scan Issue marker on a done WMS "
                            "transfer (%s). Doing so would silently rewrite the "
                            "Consumption Value report and the daily-cap counter."
                        )
                        % (rec.name or "?")
                    )
        return super().write(vals)

    @api.constrains("state", "origin", "wms_storekeeper_id", "wms_audit_legacy")
    def _check_wms_audit_trail_on_done(self):
        """Refuse to mark a WMS-originated picking 'done' unless the
        storekeeper anchor is set. The DB CHECK catches SQL / XML-RPC
        bypasses; this @api.constrains gives operators a friendly error
        through the normal write/button-validate path.
        """
        for rec in self:
            if rec.state != "done":
                continue
            if not (rec.origin or "").startswith("Barcode"):
                continue
            if rec.wms_audit_legacy:
                continue
            if not rec.wms_storekeeper_id:
                raise ValidationError(
                    _(
                        "Picking %(name)s is WMS-originated but has no storekeeper "
                        "recorded. Re-run the scan wizard to record who handled "
                        "this transfer before marking it done."
                    )
                    % {"name": rec.name}
                )

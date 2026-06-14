from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .reservation import validate_reserved_or_abort


class WmsDamage(models.Model):
    """Damage event. Confirming creates an internal stock.picking that moves
    the affected qty from its slot to the warehouse's Damage location.
    Until confirmed the record is just a draft note.
    """

    _name = "wms.damage"
    _description = "Damage event"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin",
        "wms.keeper.warning.mixin",
    ]
    _order = "create_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        tracking=True,
    )
    product_id = fields.Many2one("product.product", required=True, tracking=True)
    quantity = fields.Float(required=True, default=1.0, tracking=True)
    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "Damage quantity must be greater than zero.",
    )
    damage_value = fields.Float(
        string="Loss value",
        readonly=True,
        copy=False,
        help="Quantity x the product's unit cost at the moment the damage "
        "event was confirmed - what this loss was worth to the trust at the "
        "time it happened. NOT recomputed when quantity or cost changes "
        "later. FPAT High: the previous computed/depends pattern silently "
        "re-rated past losses whenever quantity was edited (which itself "
        "should not be allowed - see action_confirm and the readonly state "
        "on the view).",
    )

    source_slot_id = fields.Many2one(
        "stock.location",
        # Stock can live in slots (inside racks) OR floor zones (open
        # storage areas) — both count as wms storage. Mirrors the
        # STOCK_TYPES tuple in scan_receipt._auto_assign_slot so the
        # damage form can target any place where stock physically sits.
        domain=[("wms_location_type", "in", ("slot", "floor"))],
        required=True,
        tracking=True,
        ondelete="restrict",
    )
    reason = fields.Selection(
        [
            ("broken", "Broken"),
            ("expired", "Expired"),
            ("contaminated", "Contaminated"),
            ("other", "Other"),
        ],
        default="broken",
        required=True,
    )
    note = fields.Text(
        help="Free-text explanation of the damage event. Mandatory when "
        "reason='other' so the audit trail isn't a black hole — for "
        "broken/expired/contaminated the reason field already explains "
        "what happened.",
    )

    # Enforce note when reason='other' so picking "Other" doesn't bypass
    # the accountability requirement. The constraint runs at create/write
    # and on action_confirm so the damage can't escape draft state
    # without explanatory text when one is needed.
    @api.constrains("reason", "note")
    def _check_note_required_for_other(self):
        for rec in self:
            if rec.reason == "other" and not (rec.note or "").strip():
                raise ValidationError(
                    "If the damage reason is 'Other', you must write a quick "
                    "note explaining what happened (e.g., 'Spilled during "
                    "morning feed'). If the reason fits one of the pre-set "
                    "options (Broken, Expired, or Contaminated), pick that "
                    "instead."
                )

    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        compute="_compute_warehouse",
        store=True,
    )
    repair_order_id = fields.Many2one(
        "wms.repair.order",
        string="Linked repair order",
        readonly=True,
        copy=False,
        help="Set when an Admin or Store Keeper clicks 'Create Repair Order' "
        "from this damage event.",
    )

    # ---- Audit trail (matches Scan Issue) -------------------------------
    # All three required: the trust's invariant is that every stock-moving
    # action records who reported it, who authorised it, and which keeper
    # was on the desk. The action_confirm() guard re-checks this at
    # confirm-time so a record can be drafted with placeholders but never
    # committed without real names.
    wms_reported_by = fields.Char(
        string="Reported by",
        index=True,
        tracking=True,
        help="Name of the person who reported the damage (the worker who "
        "found it, the operator who broke it, etc.). Plain text — not "
        "every reporter has an Odoo account.",
    )
    wms_authorized_by = fields.Char(
        string="Authorised by",
        index=True,
        tracking=True,
        help="Name of the person who authorised filing this damage event "
        "(the cow-care lead, the Manager). Plain text.",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        tracking=True,
        domain=[("active", "=", True)],
        help="The on-duty Store Keeper who filed this damage record. "
        "Picked from the roster — same pattern as Scan Issue / Receipt.",
    )
    damage_photo = fields.Binary(
        string="Damage photo",
        attachment=True,
        help="Optional photo of the damage. On a phone/tablet the camera opens "
        "automatically. Stored as proof for the audit trail.",
    )

    @api.depends("source_slot_id")
    def _compute_warehouse(self):
        """Walk the location hierarchy upward looking for a warehouse
        binding. If no ancestor is bound to a warehouse (common for
        trust-branded top-level locations like "Dakshin Vrindavan"
        where the rack sits OUTSIDE the WH/Stock subtree), fall back
        to the active company's primary warehouse so action_confirm
        can still find a Damage location and an internal-transfer
        picking type — same pattern as the FIFO out-of-tree fallback
        in stock_location.find_oldest_quants_for_product.
        """
        Warehouse = self.env["stock.warehouse"]
        for rec in self:
            loc = rec.source_slot_id
            while loc and not loc.warehouse_id:
                loc = loc.location_id
            if loc and loc.warehouse_id:
                rec.warehouse_id = loc.warehouse_id
            else:
                rec.warehouse_id = Warehouse.search(
                    [("company_id", "=", rec.env.company.id)], limit=1
                )

    # ---- Smart "what should we do about this?" recommendation ------------
    remaining_on_hand = fields.Float(
        string="Other units on hand",
        compute="_compute_recommendation",
        help="Total quantity of this same product still sitting in other "
        "internal slots / floor zones (excludes the qty being damaged "
        "here). Drives the recommended action below.",
    )
    recommended_action = fields.Selection(
        [
            ("ok", "No action needed"),
            ("repair_returnable", "Schedule repair (returnable item, spare available)"),
            ("repair_returnable_only", "Schedule repair (returnable item, no spare!)"),
            ("repair_with_spare", "Repair if possible; spare unit covers the gap"),
            ("urgent_buy", "Urgent buy — no stock left"),
            ("note_only", "Note for future order (consumable, plenty of stock)"),
        ],
        compute="_compute_recommendation",
        store=False,
        help="Auto-derived from the product's WMS Kind and how much of it "
        "is still on hand elsewhere when the damage is recorded.",
    )
    recommendation_message = fields.Text(
        string="What to do",
        compute="_compute_recommendation",
        store=False,
        help="Plain-English explanation of the recommended action — the "
        "numbers behind it and what the Admin should kick off next.",
    )

    @api.depends("product_id", "quantity", "state")
    def _compute_recommendation(self):
        """Look at the product's WMS Kind + the leftover quantity sitting
        on other slots, then suggest one of:
          * urgent_buy — product is gone, no spare anywhere
          * repair_returnable / repair_returnable_only — fix the broken
            tool (returnable items can come back, with or without a
            spare to cover the meantime)
          * repair_with_spare — non-returnable but other units exist
            (e.g. a partially damaged consumable batch that can be
            sorted), so no rush
          * note_only — plenty on the shelf, just log it
          * ok — no product set yet, nothing to recommend
        """
        Quant = self.env["stock.quant"].sudo()
        for rec in self:
            if not rec.product_id:
                rec.remaining_on_hand = 0.0
                rec.recommended_action = "ok"
                rec.recommendation_message = ""
                continue

            # We want "what's still usable across the warehouse" — that
            # means internal storage MINUS the damage/repair stations.
            # Without this exclusion, the qty we just moved to the Damage
            # location still gets counted as "on hand" after confirm,
            # which makes the form claim 5000 still on hand right after
            # damaging 1 unit out of 5000. Misleading.
            quants = Quant.search(
                [
                    ("product_id", "=", rec.product_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("location_id.wms_is_damage", "=", False),
                    ("location_id.wms_is_repair", "=", False),
                    ("quantity", ">", 0),
                ]
            )
            total = sum(q.quantity for q in quants)
            # For a draft record the picking hasn't run yet, so subtract
            # the qty we're about to damage to show the user how many will
            # be left over once they confirm. For a confirmed record the
            # picking already moved the qty out of the source slot to the
            # Damage location — which the search above excludes — so the
            # total already reflects "what's left usable".
            if rec.state == "draft":
                remaining = max(0.0, total - (rec.quantity or 0.0))
            else:
                remaining = total
            rec.remaining_on_hand = remaining

            is_returnable = bool(rec.product_id.wms_is_returnable)
            product_name = rec.product_id.display_name
            qty = rec.quantity or 0.0
            # FPAT Critical: wms_product_kind on product.product is RELATED to the
            # field on product.template. For a related Selection, Odoo 19 sets
            # _fields[...].selection to a lambda that resolves the parent's list
            # at evaluation time - calling dict() on the lambda raises TypeError
            # ('function' is not iterable). Read the static list from the
            # template instead, so this works for both stored and related kinds.
            kind_label = dict(
                rec.product_id.product_tmpl_id._fields["wms_product_kind"].selection
            ).get(rec.product_id.wms_product_kind, "Unclassified")

            if remaining <= 0 and is_returnable:
                rec.recommended_action = "repair_returnable_only"
                rec.recommendation_message = (
                    "%g × %s is the only %s the trust owns and it's now "
                    "damaged. Open a Repair Order so it comes back fixed. "
                    "Until then, nobody can take this item — flag the Admin "
                    "if it's needed urgently for ongoing work."
                ) % (qty, product_name, kind_label)
            elif remaining <= 0 and not is_returnable:
                rec.recommended_action = "urgent_buy"
                rec.recommendation_message = (
                    "URGENT — %g × %s damaged and zero on hand elsewhere. "
                    "This is a %s, so it can't be repaired. Buy a fresh "
                    "batch immediately; this will show up under WMS → "
                    "Reports → Buying Recommendations as Critical."
                ) % (qty, product_name, kind_label)
            elif is_returnable:
                rec.recommended_action = "repair_returnable"
                rec.recommendation_message = (
                    "%g × %s damaged. %g other unit(s) still on hand, so "
                    "work isn't blocked. Open a Repair Order to bring this "
                    "one back into service."
                ) % (qty, product_name, remaining)
            elif rec.product_id.wms_product_kind in ("tool", "spare"):
                # Non-returnable but the product is a tool / spare
                # that COULD in principle be reconditioned
                # (worn drill bit, partial spool, etc.). Other units cover
                # the gap so it isn't urgent, but flag it so the Admin
                # can decide whether to repair or scrap.
                rec.recommended_action = "repair_with_spare"
                rec.recommendation_message = (
                    "%g × %s damaged, %g still on hand so work isn't "
                    "blocked. This is a %s — assess whether it can be "
                    "reconditioned or should be scrapped via the Damage "
                    "location. No urgent buy required."
                ) % (qty, product_name, remaining, kind_label)
            else:
                rec.recommended_action = "note_only"
                rec.recommendation_message = (
                    "%g × %s damaged. %g still on hand — no urgent action. "
                    "The buying-recommendation report will factor this into "
                    "the next refresh and bump the suggested order quantity "
                    "if needed."
                ) % (qty, product_name, remaining)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.damage") or "DMG/0001"
        return super().create(vals_list)

    @api.constrains("product_id", "quantity", "source_slot_id", "state")
    def _check_source_slot_stock(self):
        """Refuse to file damage for more units than the slot has FREE
        (i.e. total - reserved). Without this two failure modes are open:

          1. Operator types qty=10 on a slot that only has 3 → negative
             quants when the picking validates.
          2. Operator damages qty that another keeper has already
             reserved for an in-flight Scan Issue → the issue's planned
             quants vanish underneath it and the picking explodes on
             validate.

        Subtracting reserved_quantity closes both holes."""
        Quant = self.env["stock.quant"].sudo()
        for rec in self:
            if rec.state == "confirmed":
                continue  # already posted, don't re-validate
            if not (rec.product_id and rec.source_slot_id and rec.quantity):
                continue
            quants = Quant.search(
                [
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "=", rec.source_slot_id.id),
                ]
            )
            total = sum(quants.mapped("quantity"))
            reserved = sum(quants.mapped("reserved_quantity"))
            free = max(0.0, total - reserved)
            if rec.quantity > free + 0.0001:  # tiny float tolerance
                # Break the message into two cases so the operator
                # knows whether to recount or to wait for an in-flight
                # issue to release stock.
                if reserved > 0 and rec.quantity <= total + 0.0001:
                    raise UserError(
                        "Slot %s has %g × %s, but %g unit(s) are already "
                        "spoken for by a pending issue that hasn't finished "
                        "yet. Only %g are really free to mark as damaged. "
                        "Either wait for that issue to finish, cancel it, or "
                        "mark fewer units as damaged (up to %g)."
                        % (
                            rec.source_slot_id.display_name,
                            total,
                            rec.product_id.display_name,
                            reserved,
                            free,
                            free,
                        )
                    )
                raise UserError(
                    "You're trying to file %g × %s as damaged at slot %s, but "
                    "only %g unit(s) are actually there. Re-count the slot or "
                    "fix the quantity before confirming."
                    % (
                        rec.quantity,
                        rec.product_id.display_name,
                        rec.source_slot_id.display_name,
                        free,
                    )
                )

    # Once a damage is confirmed the loss is recorded and the stock has already
    # moved to the Damage location, so a keeper must not be able to revise it
    # over RPC. Managers (and superuser internal paths) bypass. The keeper IS
    # still allowed to link a repair order (action_create_repair_order writes
    # only repair_order_id) and chatter still works, so those fields are
    # whitelisted; every other business field is frozen once confirmed.
    _KEEPER_LOCKED_STATES = ("confirmed",)
    _KEEPER_ALLOWED_ON_LOCKED = frozenset(
        {
            "repair_order_id",
            "message_ids",
            "message_follower_ids",
            "message_partner_ids",
            "message_main_attachment_id",
            "message_is_follower",
            "activity_ids",
        }
    )

    def write(self, vals):
        """Freeze a confirmed damage against keeper edits (record-level guard).

        Defence-in-depth behind the readonly-on-confirmed form: the value is a
        frozen snapshot and the stock has moved, so editing a confirmed damage
        must not silently rewrite the loss record. Managers bypass; linking a
        repair order and chatter are still allowed (whitelisted).
        """
        if (
            not self.env.su
            and set(vals) - self._KEEPER_ALLOWED_ON_LOCKED
            and not self.env.user.has_group("wms_location.group_wms_manager")
        ):
            for rec in self:
                if rec.state in self._KEEPER_LOCKED_STATES:
                    raise AccessError(
                        "Damage %s is already confirmed — only a Manager can "
                        "change it. The loss is recorded and the stock has "
                        "moved; create a repair order if the item needs fixing." % (rec.name or "?")
                    )
        return super().write(vals)

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            # Audit-trail invariant — confirm cannot post a damage event
            # with missing names. Drafts can be saved with placeholders
            # so the operator has scratch space, but the final commit
            # must record who-reported / who-authorised / which keeper.
            missing = []
            if not (rec.wms_reported_by or "").strip():
                missing.append("Reported by")
            if not (rec.wms_authorized_by or "").strip():
                missing.append("Authorised by")
            if not rec.wms_storekeeper_id:
                missing.append("Store Keeper on duty")
            if missing:
                raise UserError(
                    "Fill in the audit-trail field(s) before confirming this "
                    "damage event: %s. The trust requires every stock-moving "
                    "action to record who reported it, who authorised it, "
                    "and which keeper was on the desk." % ", ".join(missing)
                )

            damage_loc = self.env["stock.location"].search(
                [
                    ("wms_is_damage", "=", True),
                    ("id", "child_of", rec.warehouse_id.view_location_id.id),
                ],
                limit=1,
            )
            if not damage_loc:
                raise UserError(
                    "No Damage location for warehouse %s." % rec.warehouse_id.display_name
                )

            # Use the warehouse's int_type_id m2o directly.
            # Odoo 19 archives the Internal Transfers picking type for
            # 1-step warehouses, so a plain search filtered by
            # code='internal' returns nothing (active filter excludes it).
            picking_type = rec.warehouse_id.int_type_id
            if not picking_type:
                raise UserError(
                    "Warehouse %s is not configured for internal stock transfers. "
                    "Ask an Administrator to enable internal transfers in the "
                    "Inventory settings." % rec.warehouse_id.display_name
                )
            if not picking_type.active:
                picking_type.sudo().active = True  # auto-unarchive
            # Picking inherits the damage event's audit fields so reports
            # keyed off stock.picking can read damage moves without
            # cross-referencing wms.damage. Same shape as Scan Issue.
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": rec.source_slot_id.id,
                    "location_dest_id": damage_loc.id,
                    "origin": rec.name,
                    "wms_taken_by": (rec.wms_reported_by or "").strip(),
                    "wms_ordered_by": (rec.wms_authorized_by or "").strip(),
                    "wms_storekeeper_id": rec.wms_storekeeper_id.id,
                }
            )
            self.env["stock.move"].create(
                {
                    "description_picking": "Damage: %s" % rec.product_id.display_name,
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": rec.source_slot_id.id,
                    "location_dest_id": damage_loc.id,
                }
            )
            validate_reserved_or_abort(picking, rec.product_id, "send to Damage")
            # FPAT High: snapshot the loss value at confirm time, then never
            # touch it. quantity_value-x-cost is what the loss WAS worth when
            # the damage actually happened; a later cost change or quantity
            # edit must not rewrite history.
            rec.write(
                {
                    "state": "confirmed",
                    "picking_id": picking.id,
                    "damage_value": (rec.quantity or 0.0) * (rec.product_id.standard_price or 0.0),
                }
            )

            # Mirror the audit-trail summary into the chatter so the
            # damage history stands on its own without cross-referencing
            # the picking.
            # Markup() so Odoo 19 renders the <p>/<b> tags instead of
            # escaping them to visible text in the chatter.
            audit_body = Markup(
                "<p><b>Damage confirmed.</b> "
                "Reported by <b>%s</b>; authorised by <b>%s</b>; "
                "Store Keeper on duty: <b>%s</b>.</p>"
            ) % (
                rec.wms_reported_by or "(unspecified)",
                rec.wms_authorized_by or "(unspecified)",
                rec.wms_storekeeper_id.name or "(unknown)",
            )
            rec.message_post(
                body=audit_body,
                subject="Damage audit",
                message_type="notification",
            )

            # URGENT BUY alert — ping every WMS Manager via Discuss so
            # somebody actually sees it before the daily buying-rec
            # cron rolls round.
            if rec.recommended_action == "urgent_buy":
                rec._notify_managers_urgent_buy()

    def _notify_managers_urgent_buy(self):
        """Post a Discuss notification to every WMS Manager when an
        urgent-buy damage event lands. Idempotent — runs once per
        confirm. Silently skips if no Managers are configured."""
        self.ensure_one()
        group = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not group or not group.all_user_ids:
            return
        body = Markup(
            "<p><b>⚠ URGENT BUY required.</b></p>"
            "<p>%(qty)g × <b>%(product)s</b> just got filed as damaged at "
            "<b>%(slot)s</b>, and the trust has <b>zero spares</b> of this "
            "product on hand anywhere.</p>"
            "<p>Reported by <b>%(reporter)s</b>; authorised by "
            "<b>%(auth)s</b>; Store Keeper on duty: "
            "<b>%(keeper)s</b>.</p>"
            "<p>Open <i>WMS → Reports → Buying Recommendations</i> — this "
            "product will jump to Critical on the next refresh.</p>"
        ) % {
            "qty": self.quantity,
            "product": self.product_id.display_name,
            "slot": self.source_slot_id.display_name,
            "reporter": self.wms_reported_by or "(unspecified)",
            "auth": self.wms_authorized_by or "(unspecified)",
            "keeper": (self.wms_storekeeper_id.name if self.wms_storekeeper_id else "(unknown)"),
        }
        # message_notify -> Discuss Inbox + systray. A plain message_post on
        # a partner only reaches followers; a user is NOT a follower of their
        # own contact, so the previous loop was silently dropping urgent-buy
        # alerts. See addons/wms_reports/models/wms_notify.py for the rationale.
        self.env["mail.thread"].message_notify(
            partner_ids=group.all_user_ids.partner_id.ids,
            body=body,
            subject="WMS - URGENT BUY: %s" % self.product_id.display_name,
        )

    def action_create_repair_order(self):
        """Open a new wms.repair.order pre-filled from this damage event.
        Used by the Create Repair Order button on the damage form."""
        self.ensure_one()
        if self.repair_order_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "wms.repair.order",
                "res_id": self.repair_order_id.id,
                "view_mode": "form",
            }
        repair = self.env["wms.repair.order"].create(
            {
                "damage_id": self.id,
                "product_id": self.product_id.id,
                "quantity": self.quantity,
                "original_slot_id": self.source_slot_id.id,
                "return_slot_id": self.source_slot_id.id,
                "wms_reported_by": self.wms_reported_by,
                "wms_authorized_by": self.wms_authorized_by,
                "wms_storekeeper_id": self.wms_storekeeper_id.id,
            }
        )
        self.repair_order_id = repair.id
        return {
            "type": "ir.actions.act_window",
            "name": "Repair order for %s" % self.product_id.display_name,
            "res_model": "wms.repair.order",
            "res_id": repair.id,
            "view_mode": "form",
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == "confirmed":
                raise UserError(
                    "Cancel the stock transfer that was created for this damage event before cancelling the record."
                )
            rec.state = "cancelled"

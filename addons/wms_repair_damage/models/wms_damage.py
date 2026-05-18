from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsDamage(models.Model):
    """Damage event. Confirming creates an internal stock.picking that moves
    the affected qty from its slot to the warehouse's Damage location.
    Until confirmed the record is just a draft note.
    """

    _name = "wms.damage"
    _description = "Damage event"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        default="draft",
        tracking=True,
    )
    product_id = fields.Many2one("product.product", required=True, tracking=True)
    quantity = fields.Float(required=True, default=1.0, tracking=True)
    source_slot_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "=", "slot")],
        required=True,
        tracking=True,
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
    note = fields.Text()
    picking_id = fields.Many2one("stock.picking", readonly=True, copy=False)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        compute="_compute_warehouse",
        store=True,
    )

    @api.depends("source_slot_id")
    def _compute_warehouse(self):
        for rec in self:
            loc = rec.source_slot_id
            while loc and not loc.warehouse_id:
                loc = loc.location_id
            rec.warehouse_id = loc.warehouse_id if loc else False

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

            quants = Quant.search(
                [
                    ("product_id", "=", rec.product_id.id),
                    ("location_id.usage", "=", "internal"),
                    ("quantity", ">", 0),
                ]
            )
            total = sum(q.quantity for q in quants)
            # The damaged qty hasn't been moved yet for a draft record;
            # for a confirmed one the picking already removed it from the
            # source slot, so the leftover total already excludes it.
            if rec.state == "draft":
                remaining = max(0.0, total - (rec.quantity or 0.0))
            else:
                remaining = total
            rec.remaining_on_hand = remaining

            is_returnable = bool(rec.product_id.wms_is_returnable)
            product_name = rec.product_id.display_name
            qty = rec.quantity or 0.0
            kind_label = dict(
                rec.product_id._fields["wms_product_kind"].selection
                if not callable(rec.product_id._fields["wms_product_kind"].selection)
                else self.env["product.product"]
                .fields_get(["wms_product_kind"])
                .get("wms_product_kind", {})
                .get("selection", [])
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

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
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
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": rec.source_slot_id.id,
                    "location_dest_id": damage_loc.id,
                    "origin": rec.name,
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
            picking.action_confirm()
            picking.action_assign()
            for ml in picking.move_ids.move_line_ids:
                if not ml.quantity:
                    ml.quantity = ml.quantity_product_uom or picking.move_ids[:1].product_uom_qty
            picking.button_validate()
            rec.write({"state": "confirmed", "picking_id": picking.id})

    def action_cancel(self):
        for rec in self:
            if rec.state == "confirmed":
                raise UserError(
                    "Cancel the stock transfer that was created for this damage event before cancelling the record."
                )
            rec.state = "cancelled"

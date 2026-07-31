import logging

from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError

from .reservation import validate_reserved_or_abort

_logger = logging.getLogger(__name__)


class WmsRepairOrder(models.Model):
    """Repair workflow: damaged → in_repair → done / scrapped.

    Generates internal pickings:
      - start_repair : Damage location → Repair-Out
      - finish_repair: Repair-Out      → original slot (or operator override)

    Scrap path uses Odoo's native stock.scrap from Repair-Out.
    """

    _name = "wms.repair.order"
    _description = "Repair order"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin",
        "wms.keeper.warning.mixin",
    ]
    _order = "create_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_repair", "In repair"),
            ("done", "Done"),
            ("scrapped", "Scrapped"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    damage_id = fields.Many2one("wms.damage")
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(required=True, default=1.0)
    _quantity_positive = models.Constraint(
        "CHECK(quantity > 0)",
        "Repair quantity must be greater than zero.",
    )
    original_slot_id = fields.Many2one(
        "stock.location",
        # Same widened domain as wms.damage.source_slot_id — stock can
        # live in slots OR floor zones, so a repair can originate from
        # either.
        domain=[("wms_location_type", "in", ("slot", "floor"))],
        ondelete="restrict",
        help="Where the item came from; default destination after repair.",
    )
    return_slot_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "in", ("slot", "floor"))],
        ondelete="restrict",
        help="Where the item goes after repair completes. Defaults to original.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        compute="_compute_warehouse",
        store=True,
    )
    technician_id = fields.Many2one("res.users")
    start_picking_id = fields.Many2one("stock.picking", readonly=True)
    finish_picking_id = fields.Many2one("stock.picking", readonly=True)
    repair_notes = fields.Text()

    # ---- Audit trail (matches wms.damage and Scan Issue) ---------------
    wms_reported_by = fields.Char(
        string="Reported by",
        index=True,
        tracking=True,
        help="Name of the person who flagged this item for repair. "
        "Pre-filled from the linked damage event when applicable.",
    )
    wms_authorized_by = fields.Char(
        string="Authorised by",
        index=True,
        tracking=True,
        help="Name of the person who authorised the repair (Manager / "
        "cow-care lead). Pre-filled from the damage event.",
    )
    wms_storekeeper_id = fields.Many2one(
        "wms.storekeeper",
        string="Store Keeper on duty",
        index=True,
        tracking=True,
        domain=[("active", "=", True)],
        help="The on-duty Store Keeper who logged this repair order.",
    )

    @api.depends("original_slot_id")
    def _compute_warehouse(self):
        """Walk up looking for a warehouse binding, then fall back to
        the active company's primary warehouse. Matches the same
        out-of-tree rescue used on wms.damage / FIFO planner — a rack
        parked under a branded top-level location (no warehouse_id on
        the ancestors) still gets a sensible default so the picking
        type lookup downstream succeeds.
        """
        Warehouse = self.env["stock.warehouse"]
        for rec in self:
            loc = rec.original_slot_id
            while loc and not loc.warehouse_id:
                loc = loc.location_id
            if loc and loc.warehouse_id:
                rec.warehouse_id = loc.warehouse_id
            else:
                rec.warehouse_id = Warehouse.search(
                    [("company_id", "=", rec.env.company.id)], limit=1
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.repair") or "REP/0001"
        return super().create(vals_list)

    def _find_location(self, flag):
        return self.env["stock.location"].search(
            [
                (flag, "=", True),
                ("id", "child_of", self.warehouse_id.view_location_id.id),
            ],
            limit=1,
        )

    def _internal_picking_type(self):
        """Returns the warehouse's Internal Transfers picking type.

        Odoo 19 archives this for 1-step warehouses, so a plain search by
        code='internal' returns empty (active filter). Reading the m2o
        directly avoids that; we auto-unarchive if needed so subsequent
        pickings don't fail.
        """
        ptype = self.warehouse_id.int_type_id
        if ptype and not ptype.active:
            ptype.sudo().active = True
        return ptype

    def _check_audit_complete(self):
        """Shared guard: a repair order can be drafted with placeholders,
        but moving it past draft requires the audit triplet — same
        invariant as wms.damage.action_confirm."""
        self.ensure_one()
        missing = []
        if not (self.wms_reported_by or "").strip():
            missing.append("Reported by")
        if not (self.wms_authorized_by or "").strip():
            missing.append("Authorised by")
        if not self.wms_storekeeper_id:
            missing.append("Store Keeper on duty")
        if missing:
            raise UserError(
                "Fill in the audit-trail field(s) before moving this repair "
                "order: %s." % ", ".join(missing)
            )

    def _audit_picking_vals(self):
        """Audit fields shared by start/finish pickings — keeps reports
        keyed off stock.picking working without cross-referencing
        wms.repair.order."""
        self.ensure_one()
        return {
            "wms_taken_by": (self.wms_reported_by or "").strip(),
            "wms_ordered_by": (self.wms_authorized_by or "").strip(),
            "wms_storekeeper_id": self.wms_storekeeper_id.id,
        }

    def action_start_repair(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec._check_audit_complete()
            damage_loc = rec._find_location("wms_is_damage")
            repair_loc = rec._find_location("wms_is_repair")
            if not (damage_loc and repair_loc):
                raise UserError(
                    "Damage / Repair locations missing for %s." % rec.warehouse_id.display_name
                )
            picking_vals = {
                "picking_type_id": rec._internal_picking_type().id,
                "location_id": damage_loc.id,
                "location_dest_id": repair_loc.id,
                "origin": rec.name,
            }
            picking_vals.update(rec._audit_picking_vals())
            picking = self.env["stock.picking"].create(picking_vals)
            self.env["stock.move"].create(
                {
                    "description_picking": "Send to repair: %s" % rec.product_id.display_name,
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": damage_loc.id,
                    "location_dest_id": repair_loc.id,
                }
            )
            validate_reserved_or_abort(picking, rec.product_id, "send to Repair")
            rec.write({"state": "in_repair", "start_picking_id": picking.id})
            rec._post_state_audit(
                "Repair started",
                "Item moved from Damage to Repair-Out and is now in the technician's hands.",
            )

    def action_finish_repair(self):
        for rec in self:
            if rec.state != "in_repair":
                continue
            repair_loc = rec._find_location("wms_is_repair")
            dest = rec.return_slot_id or rec.original_slot_id
            if not dest:
                raise UserError("No destination slot.")
            picking_vals = {
                "picking_type_id": rec._internal_picking_type().id,
                "location_id": repair_loc.id,
                "location_dest_id": dest.id,
                "origin": rec.name,
            }
            picking_vals.update(rec._audit_picking_vals())
            picking = self.env["stock.picking"].create(picking_vals)
            self.env["stock.move"].create(
                {
                    "description_picking": "Return from repair: %s" % rec.product_id.display_name,
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": repair_loc.id,
                    "location_dest_id": dest.id,
                }
            )
            validate_reserved_or_abort(picking, rec.product_id, "return from Repair")
            rec.write({"state": "done", "finish_picking_id": picking.id})
            rec._post_state_audit(
                "Repair done",
                "Item returned to slot %s and is available for issue again." % dest.display_name,
            )
            rec._notify_managers_repair_done(dest)

    def _notify_managers_repair_done(self, dest):
        """Best-effort in-app notice (Batch 6): tell WMS managers a repair
        finished so they know the item is back in stock. Never raises."""
        self.ensure_one()
        try:
            managers = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
            if not managers or not managers.all_user_ids:
                return
            body = Markup(
                "<p>&#128295; <b>Repair finished: %s</b></p>"
                "<p><b>%s</b> is back in slot %s and available to issue again.</p>"
            ) % (self.name or "", self.product_id.display_name, dest.display_name)
            # message_notify -> lands in each manager's Inbox + systray (a plain
            # message_post on a partner only reaches followers).
            self.env["mail.thread"].message_notify(
                partner_ids=managers.all_user_ids.partner_id.ids,
                body=body,
                subject="WMS — Repair finished",
            )
        except Exception:  # noqa: BLE001 - a notice must never break the repair
            _logger.exception("wms.repair.order: repair-done notify failed")

    def action_scrap(self):
        for rec in self:
            if rec.state != "in_repair":
                raise UserError("Only in-repair items can be scrapped.")
            repair_loc = rec._find_location("wms_is_repair")
            scrap = self.env["stock.scrap"].create(
                {
                    "product_id": rec.product_id.id,
                    "scrap_qty": rec.quantity,
                    "location_id": repair_loc.id,
                    "product_uom_id": rec.product_id.uom_id.id,
                    "origin": rec.name,
                }
            )
            # Serialise against a concurrent Scan Issue / repair-finish on the
            # same product so the write-off can't race the reservation.
            self.env.cr.execute(
                "SELECT id FROM product_product WHERE id = %s FOR UPDATE",
                (rec.product_id.id,),
            )
            scrap.action_validate()
            rec.state = "scrapped"
            rec._post_state_audit(
                "Scrapped",
                "Item could not be repaired and has been written off from "
                "the Repair-Out location.",
            )

    def action_cancel(self):
        """Cancel a draft repair order (no stock has moved yet).
        In-repair / done / scrapped orders can't be cancelled — that
        would orphan the matching stock moves."""
        for rec in self:
            if rec.state in ("done", "scrapped"):
                raise UserError(
                    "This repair order is already %s — cancelling would "
                    "orphan the stock moves it generated. Open a new "
                    "damage event if the item needs to leave service again." % rec.state
                )
            if rec.state == "in_repair":
                raise UserError(
                    "Item is currently at the Repair-Out location. Either "
                    "finish the repair (Mark Done) or scrap it before "
                    "cancelling — otherwise the unit stays stuck in "
                    "Repair-Out with no owner."
                )
            rec.state = "cancelled"
            rec._post_state_audit(
                "Cancelled",
                "Draft repair order cancelled before any stock movement.",
            )

    def _post_state_audit(self, headline, detail):
        """Mirror the audit-trail summary into chatter so the repair
        order's history stands on its own without cross-referencing the
        picking. Same pattern as wms.damage.action_confirm."""
        self.ensure_one()
        # Markup() tells Odoo this body is already safe HTML; without it,
        # Odoo 19 escapes the angle brackets and the <p>/<b> tags display
        # literally in the chatter.
        body = Markup(
            "<p><b>%(headline)s.</b> %(detail)s</p>"
            "<p>Reported by <b>%(reporter)s</b>; authorised by "
            "<b>%(auth)s</b>; Store Keeper on duty: "
            "<b>%(keeper)s</b>; logged in as: <b>%(login)s</b>.</p>"
        ) % {
            "headline": headline,
            "detail": detail,
            "reporter": self.wms_reported_by or "(unspecified)",
            "auth": self.wms_authorized_by or "(unspecified)",
            "keeper": (self.wms_storekeeper_id.name if self.wms_storekeeper_id else "(unknown)"),
            "login": self.env.user.display_name or "(system)",
        }
        self.message_post(
            body=body,
            subject="Repair audit",
            message_type="notification",
        )

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsRepairOrder(models.Model):
    """Repair workflow: damaged → in_repair → done / scrapped.

    Generates internal pickings:
      - start_repair : Damage location → Repair-Out
      - finish_repair: Repair-Out      → original slot (or operator override)

    Scrap path uses Odoo's native stock.scrap from Repair-Out.
    """

    _name = "wms.repair.order"
    _description = "Repair order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    original_slot_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "=", "slot")],
        help="Where the item came from; default destination after repair.",
    )
    return_slot_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "=", "slot")],
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
        for rec in self:
            loc = rec.original_slot_id
            while loc and not loc.warehouse_id:
                loc = loc.location_id
            rec.warehouse_id = loc.warehouse_id if loc else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("wms.repair") or "REP/0001"
                )
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

    def action_start_repair(self):
        for rec in self:
            if rec.state != "draft":
                continue
            damage_loc = rec._find_location("wms_is_damage")
            repair_loc = rec._find_location("wms_is_repair")
            if not (damage_loc and repair_loc):
                raise UserError(
                    "Damage / Repair locations missing for %s."
                    % rec.warehouse_id.display_name
                )
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": rec._internal_picking_type().id,
                    "location_id": damage_loc.id,
                    "location_dest_id": repair_loc.id,
                    "origin": rec.name,
                }
            )
            self.env["stock.move"].create(
                {
                    "description_picking": "Send to repair: %s"
                    % rec.product_id.display_name,
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": damage_loc.id,
                    "location_dest_id": repair_loc.id,
                }
            )
            picking.action_confirm()
            picking.action_assign()
            for ml in picking.move_ids.move_line_ids:
                if not ml.quantity:
                    ml.quantity = (
                        ml.quantity_product_uom or picking.move_ids[:1].product_uom_qty
                    )
            picking.button_validate()
            rec.write({"state": "in_repair", "start_picking_id": picking.id})

    def action_finish_repair(self):
        for rec in self:
            if rec.state != "in_repair":
                continue
            repair_loc = rec._find_location("wms_is_repair")
            dest = rec.return_slot_id or rec.original_slot_id
            if not dest:
                raise UserError("No destination slot.")
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": rec._internal_picking_type().id,
                    "location_id": repair_loc.id,
                    "location_dest_id": dest.id,
                    "origin": rec.name,
                }
            )
            self.env["stock.move"].create(
                {
                    "description_picking": "Return from repair: %s"
                    % rec.product_id.display_name,
                    "product_id": rec.product_id.id,
                    "product_uom_qty": rec.quantity,
                    "product_uom": rec.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": repair_loc.id,
                    "location_dest_id": dest.id,
                }
            )
            picking.action_confirm()
            picking.action_assign()
            for ml in picking.move_ids.move_line_ids:
                if not ml.quantity:
                    ml.quantity = (
                        ml.quantity_product_uom or picking.move_ids[:1].product_uom_qty
                    )
            picking.button_validate()
            rec.write({"state": "done", "finish_picking_id": picking.id})

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
            scrap.action_validate()
            rec.state = "scrapped"

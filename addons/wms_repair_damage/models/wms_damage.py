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
                    "Warehouse %s has no Internal Transfer picking type. "
                    "Enable multi-step routes in Inventory settings."
                    % rec.warehouse_id.display_name
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
                raise UserError("Cancel the underlying picking first.")
            rec.state = "cancelled"

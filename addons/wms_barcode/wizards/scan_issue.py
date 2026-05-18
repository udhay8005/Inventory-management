from odoo import api, fields, models
from odoo.exceptions import UserError


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
        required=True,
        domain=[("usage", "in", ("customer", "production", "internal"))],
        default=lambda s: s.env.ref("stock.stock_location_customers"),
    )
    last_scan = fields.Char()
    requested_qty = fields.Float(default=1.0)
    feedback = fields.Char(readonly=True)

    plan_line_ids = fields.One2many("wms.scan.issue.plan", "wizard_id")
    short_qty = fields.Float(readonly=True, help="Shortfall — what we couldn't allocate.")

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

    @api.depends("plan_line_ids.product_id")
    def _compute_photo_required(self):
        # UoM whose category != 'Units' (i.e. measured, not counted).
        unit_cat = self.env.ref("uom.product_uom_categ_unit", raise_if_not_found=False)
        for wiz in self:
            wiz.photo_required = (
                any(
                    ln.product_id.uom_id.category_id != unit_cat
                    for ln in wiz.plan_line_ids
                    if ln.product_id
                )
                if unit_cat
                else False
            )

    def on_barcode_scanned(self, barcode):
        """Auto-plan FIFO deduction when a scan is detected.
        Uses the current `requested_qty` (default 1) — operator can
        adjust qty between scans for bulk items.
        """
        self.last_scan = barcode
        return self.action_plan()

    def action_plan(self):
        self.ensure_one()
        if not self.last_scan:
            raise UserError("Scan a product first.")
        info = self.env["wms.barcode.alias"].resolve(self.last_scan)
        if info.get("kind") not in ("product", "alias", "lot"):
            raise UserError("Barcode does not resolve to a product.")

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
            self.env["wms.scan.issue.plan"].create(
                {
                    "wizard_id": self.id,
                    "product_id": product.id,
                    "quant_id": quant.id,
                    "location_id": quant.location_id.id,
                    "in_date": quant.in_date,
                    "available": quant.quantity - quant.reserved_quantity,
                    "take": take,
                }
            )
        self.short_qty = missing
        self.feedback = "Planned %s × %s across %d slot(s)%s" % (
            qty,
            product.display_name,
            len(plan),
            f"; short by {missing}" if missing else "",
        )
        return self._reopen()

    def action_validate(self):
        self.ensure_one()
        if not self.plan_line_ids:
            raise UserError("Nothing planned yet.")
        if self.short_qty:
            raise UserError("Cannot validate: short by %s." % self.short_qty)
        if self.photo_required and not self.photo:
            raise UserError(
                "This item is measured (liters / kg / etc.). "
                "Please attach a photo of what's being issued before validating."
            )

        # Pick a picking type via warehouse-level m2o so we don't get bitten
        # by Odoo 19 archiving the internal type for 1-step warehouses.
        if self.destination_id.usage == "customer":
            picking_type = self.warehouse_id.out_type_id
        else:
            picking_type = self.warehouse_id.int_type_id
        if not picking_type:
            raise UserError(
                "Warehouse %s isn't configured for this kind of stock issue. "
                "Ask an Administrator to enable the relevant operation type "
                "in the Inventory settings." % self.warehouse_id.display_name
            )
        if not picking_type.active:
            picking_type.sudo().active = True

        # Group plan lines by source so we make one move per (product, source).
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.warehouse_id.lot_stock_id.id,
                "location_dest_id": self.destination_id.id,
                "origin": "Barcode FIFO issue",
            }
        )
        for line in self.plan_line_ids:
            move = self.env["stock.move"].create(
                {
                    "description_picking": line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.take,
                    "product_uom": line.product_id.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": line.location_id.id,
                    "location_dest_id": self.destination_id.id,
                }
            )
            move._action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            for ml in move.move_line_ids:
                if not ml.quantity:
                    ml.quantity = ml.quantity_product_uom or move.product_uom_qty
        picking.button_validate()

        # Attach the photo (if any) so it's visible from the picking's
        # chatter and survives in the audit trail. We always store it
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

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Scan Issue (FIFO)",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class WmsScanIssuePlan(models.TransientModel):
    _name = "wms.scan.issue.plan"
    _description = "Planned deduction line (FIFO)"
    _order = "in_date asc"

    wizard_id = fields.Many2one("wms.scan.issue", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", required=True)
    quant_id = fields.Many2one("stock.quant")
    location_id = fields.Many2one("stock.location", string="Slot")
    in_date = fields.Datetime()
    available = fields.Float()
    take = fields.Float()

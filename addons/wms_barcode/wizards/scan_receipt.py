from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsScanReceipt(models.TransientModel):
    """Scan-based receipt: build a list of (product, qty, slot) lines
    by repeatedly scanning, then validate to create a stock.picking
    of type 'incoming' against the warehouse stock location.
    """
    _name = "wms.scan.receipt"
    _description = "Scan-based receipt"

    warehouse_id = fields.Many2one(
        "stock.warehouse", required=True,
        default=lambda s: s.env["stock.warehouse"].search([], limit=1),
    )
    last_scan = fields.Char(string="Scan here", help="Cursor stays here; HID barcode scanners emit ENTER.")
    feedback = fields.Char(readonly=True)
    line_ids = fields.One2many("wms.scan.receipt.line", "wizard_id")

    def action_process_scan(self):
        self.ensure_one()
        if not self.last_scan:
            return self._reopen()
        info = self.env["wms.barcode.alias"].resolve(self.last_scan)
        kind = info.get("kind")

        if kind in ("product", "alias", "lot"):
            self.env["wms.scan.receipt.line"].create({
                "wizard_id": self.id,
                "product_id": info["product"].id,
                "quantity": info.get("units", 1.0),
                "lot_id": info["lot"].id if kind == "lot" else False,
            })
            self.feedback = "Added %s × %s" % (info.get("units", 1.0), info["product"].display_name)
        elif kind == "location":
            # Apply this slot to the most recent line that has no destination yet.
            target = self.line_ids.filtered(lambda l: not l.location_dest_id)[-1:]
            if not target:
                self.feedback = "No pending line for slot %s" % info["location"].display_name
            else:
                target.location_dest_id = info["location"].id
                self.feedback = "Slot %s assigned" % info["location"].display_name
        else:
            self.feedback = "Unknown barcode: %s" % self.last_scan

        self.last_scan = False
        return self._reopen()

    def action_validate(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("No lines to receive.")

        # Auto-assign slot if operator didn't.
        for line in self.line_ids:
            if not line.location_dest_id:
                line.location_dest_id = self._auto_assign_slot(line.product_id, line.quantity)

        picking_type = self.env["stock.picking.type"].search([
            ("warehouse_id", "=", self.warehouse_id.id),
            ("code", "=", "incoming"),
        ], limit=1)
        if not picking_type:
            raise UserError("No incoming picking type on warehouse.")

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.warehouse_id.lot_stock_id.id,
            "origin": "Barcode scan",
        })
        for line in self.line_ids:
            self.env["stock.move"].create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.product_id.uom_id.id,
                "picking_id": picking.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": line.location_dest_id.id,
            })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            for ml in move.move_line_ids:
                ml.quantity = ml.reserved_uom_qty or ml.quantity
        picking.button_validate()

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
        }

    def _auto_assign_slot(self, product, qty):
        """Pick a slot: same-product preference, then empty, then any slot."""
        Loc = self.env["stock.location"]
        stock_loc = self.warehouse_id.lot_stock_id

        # 1. slot already holding this product with headroom
        candidate = Loc.search([
            ("id", "child_of", stock_loc.id),
            ("wms_location_type", "=", "slot"),
            ("wms_product_ids", "in", product.id),
        ], limit=1)
        if candidate:
            return candidate.id

        # 2. an empty slot
        candidate = Loc.search([
            ("id", "child_of", stock_loc.id),
            ("wms_location_type", "=", "slot"),
            ("wms_current_qty", "=", 0),
        ], limit=1)
        if candidate:
            return candidate.id

        # 3. anything
        candidate = Loc.search([
            ("id", "child_of", stock_loc.id),
            ("wms_location_type", "=", "slot"),
        ], limit=1)
        if not candidate:
            raise UserError("No slots configured in warehouse %s." % self.warehouse_id.display_name)
        return candidate.id

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class WmsScanReceiptLine(models.TransientModel):
    _name = "wms.scan.receipt.line"
    _description = "Receipt scan line"

    wizard_id = fields.Many2one("wms.scan.receipt", ondelete="cascade", required=True)
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(default=1.0, required=True)
    lot_id = fields.Many2one("stock.lot")
    location_dest_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "=", "slot")],
        help="Leave empty to let auto-assign pick a slot at validate.",
    )

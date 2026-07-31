"""V20-012 — lot-aware issue reversal (Undo).

The v19 Undo (stock.picking.action_wms_undo) builds a compensating internal
move from the issue destination back to the source slot, with NO lot on the
move — so action_assign auto-picks a lot at the destination (FEFO order), which
need not be the SAME batch that was issued. For a lot-tracked perishable that
breaks batch traceability: issue Lot A, undo, and a different Lot B sitting at
the destination could be restored instead.

This override restores the EXACT original lot. It delegates to the unchanged
v19 method for non-lot issues (every existing Undo flow + test), and for a
lot-tracked issue re-runs the v19 reversal but re-pins each reverse move to its
original lot via _do_unreserve() + _update_reserved_quantity(lot_id=...) (the
unreserve-first sequence is required — action_assign auto-reserves FEFO first,
and stacking a second reservation would over-reserve). The original "must fully
reserve or abort — never force a phantom move" safety rail is preserved: if the
exact lot is no longer at the destination, the reverse move stays unassigned
and the whole undo aborts. No new lot is ever created.
"""

from markupsafe import Markup
from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_wms_undo(self):
        self.ensure_one()
        done_lines = self.move_line_ids.filtered(lambda ml: ml.quantity)
        if not any(ml.lot_id for ml in done_lines):
            # No lot identity to preserve — the v19 reversal is exactly right.
            return super().action_wms_undo()

        # Lot-tracked issue: same reversal as v19, but each reverse move is
        # re-pinned to the lot it originally moved.
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
                "origin": "Undo: %s" % (self.name or ""),
                "wms_is_undo": True,
                "wms_storekeeper_id": self.wms_storekeeper_id.id,
            }
        )
        move_to_lot = []
        for ml in lines:
            move = self.env["stock.move"].create(
                {
                    "description_picking": "Undo %s" % (ml.product_id.display_name),
                    "product_id": ml.product_id.id,
                    "product_uom_qty": ml.quantity,
                    "product_uom": ml.product_uom_id.id,
                    "picking_id": reverse.id,
                    "location_id": ml.location_dest_id.id,
                    "location_dest_id": ml.location_id.id,
                }
            )
            move_to_lot.append((move, ml.lot_id, ml.quantity, ml.location_dest_id))
        reverse.action_confirm()
        reverse.action_assign()
        # V20-012: re-pin each reverse move to the ORIGINAL lot so the restore
        # returns the exact batch that was issued (not whatever FEFO picked).
        for move, lot, qty, src_loc in move_to_lot:
            if lot:
                move._do_unreserve()
                move._update_reserved_quantity(qty, src_loc, lot_id=lot)
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

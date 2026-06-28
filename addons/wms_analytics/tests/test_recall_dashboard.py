"""Wave 2 — Recall Dashboard: per-recall roll-ups of the recalled lots'
issued / on-hand / destroyed / returned quantities."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestRecallDashboard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Recall activation is manager-gated.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]

        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RECALL Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "RECALL Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "tracking": "lot",
                "barcode": "RECALLMED01",
            }
        )

    def _lot(self, name, on_hand):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
            }
        )
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(
                self.med, self.floor, on_hand, lot_id=lot
            )
        return lot

    def _done_move(self, lot, qty, src, dst):
        """Create and complete one move line of `lot` from `src` to `dst`."""
        move = self.env["stock.move"].create(
            {
                "description_picking": "RECALL move",
                "product_id": self.med.id,
                "product_uom_qty": qty,
                "product_uom": self.med.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dst.id,
            }
        )
        move._action_confirm()
        # Drop any auto-created (lineless) reservation line so the only line
        # _action_done sees is ours, carrying the lot — needed for a move whose
        # source is external (a return) where assign can't reserve a lot.
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.med.id,
                "lot_id": lot.id,
                "quantity": qty,
                "location_id": src.id,
                "location_dest_id": dst.id,
            }
        )
        move.picked = True
        move._action_done()
        return move

    def _recall(self, lots):
        rec = self.env["wms.lot.recall"].create(
            {
                "mode": "manual",
                "reason": "test recall",
                "lot_ids": [(6, 0, lots.ids)],
            }
        )
        rec.action_recall()
        self.env.flush_all()
        rec.invalidate_recordset()
        return rec

    def test_remaining_and_open(self):
        # One lot, 100 on hand, recalled & active → still on hand 100, open.
        lot = self._lot("RC-ONHAND", 100)
        rec = self._recall(lot)
        self.assertEqual(rec.remaining_quantity, 100.0)
        self.assertTrue(rec.is_open)
        self.assertEqual(rec.issued_quantity, 0.0)
        self.assertEqual(rec.returned_quantity, 0.0)

    def test_issued_out_move_counted(self):
        # 100 on hand, issue 40 to the customer → issued 40, remaining 60.
        lot = self._lot("RC-ISSUE", 100)
        self._done_move(lot, 40, self.floor, self.customer)
        rec = self._recall(lot)
        self.assertEqual(rec.issued_quantity, 40.0)
        self.assertEqual(rec.remaining_quantity, 60.0)

    def test_returned_in_move_counted(self):
        # A return: customer -> internal of 15 units counts as returned.
        lot = self._lot("RC-RETURN", 50)
        self._done_move(lot, 15, self.customer, self.floor)
        rec = self._recall(lot)
        self.assertEqual(rec.returned_quantity, 15.0)

    def test_destroyed_quantity_and_released_closes(self):
        # Lot flipped to destroyed lifecycle state → destroyed_quantity = on-hand.
        lot = self._lot("RC-DESTROY", 30)
        rec = self._recall(lot)
        lot.wms_lot_state = "destroyed"
        rec.invalidate_recordset()
        self.assertEqual(rec.destroyed_quantity, 30.0)
        # Releasing the recall clears the open flag.
        # (lot stays destroyed; release only flips lots still in 'recalled'.)
        rec.action_release()
        rec.invalidate_recordset()
        self.assertFalse(rec.is_open)

"""V20-012 — Undo of a lot-tracked issue restores the EXACT original lot
(batch/expiry identity), never a different lot the destination happens to hold."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestReversalLot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "RL Keeper"})
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "RL Slot",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "RL Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "RLMED01",
            }
        )
        cls.env["ir.config_parameter"].sudo().set_param("wms_reports.undo_minutes", "15")

    def _lot(self, name, expiry):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": expiry,
            }
        )

    def _issue(self, qty):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": self.med.barcode,
                "requested_qty": qty,
                "storekeeper_id": self.keeper.id,
                "taken_by": "RL Taker",
                "ordered_by": "RL Orderer",
                "usage_note": "reversal test",
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        return wiz.picking_id

    def _slot_qty(self, lot):
        return self.env["stock.quant"]._get_available_quantity(self.med, self.slot, lot_id=lot)

    def test_undo_restores_original_lot(self):
        lot = self._lot("RL-A", "2027-06-30 00:00:00")
        self.env["stock.quant"]._update_available_quantity(self.med, self.slot, 5, lot_id=lot)
        picking = self._issue(3)
        self.assertEqual(self._slot_qty(lot), 2.0, "3 of 5 issued from the lot")
        picking.action_wms_undo()
        self.assertTrue(picking.wms_reversed_by_id)
        self.assertEqual(self._slot_qty(lot), 5.0, "undo restores the 3 back to the SAME lot")

    def test_undo_restores_correct_lot_not_fefo_pick(self):
        # Lot A expires earlier (FEFO-first), Lot B later. Issue empties A then
        # draws B. Undo the B issue: it must restore Lot B — even though the
        # destination also holds Lot A, which a naive FEFO restore would grab.
        lot_a = self._lot("RL-EARLY", "2027-03-31 00:00:00")
        lot_b = self._lot("RL-LATE", "2027-12-31 00:00:00")
        self.env["stock.quant"]._update_available_quantity(self.med, self.slot, 5, lot_id=lot_a)
        self.env["stock.quant"]._update_available_quantity(self.med, self.slot, 5, lot_id=lot_b)
        self._issue(5)  # FEFO -> Lot A (empties it)
        issue_b = self._issue(5)  # A empty -> Lot B
        # Sanity: the second issue moved Lot B.
        self.assertEqual(issue_b.move_line_ids.lot_id, lot_b, "second issue drew the later lot B")
        self.assertEqual(self._slot_qty(lot_a), 0.0)
        self.assertEqual(self._slot_qty(lot_b), 0.0)

        issue_b.action_wms_undo()

        self.assertEqual(self._slot_qty(lot_b), 5.0, "undo of the Lot-B issue restores Lot B")
        self.assertEqual(self._slot_qty(lot_a), 0.0, "Lot A is NOT wrongly restored to the slot")

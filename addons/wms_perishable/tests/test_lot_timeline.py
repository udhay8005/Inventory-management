"""V20-017 — the lot timeline counts a lot's completed movements and opens
its immutable done move-line history."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLotTimeline(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "TL Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "TL Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "TL Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "TLMED01",
            }
        )

    def _receive(self, batch, qty=10):
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.med.id,
                "quantity": qty,
                "location_dest_id": self.floor.id,
                "wms_batch": batch,
                "wms_expiry": "2027-12-31",
            }
        )
        wiz.action_validate()
        return self.env["stock.lot"].search(
            [("product_id", "=", self.med.id), ("name", "=", batch)], limit=1
        )

    def test_timeline_counts_and_opens_movements(self):
        lot = self._receive("TL-A")
        self.assertTrue(lot, "the receipt created the batch lot")
        self.assertGreaterEqual(lot.wms_movement_count, 1, "the receipt is a movement on the lot")
        action = lot.action_wms_lot_timeline()
        self.assertEqual(action["res_model"], "stock.move.line")
        lines = self.env["stock.move.line"].search(action["domain"])
        self.assertTrue(lines, "the timeline lists the receipt move line")
        self.assertTrue(all(ml.lot_id == lot for ml in lines), "timeline is scoped to this lot")

    def test_lifecycle_fields_present(self):
        lot = self._receive("TL-B")
        # The lot carries its lifecycle state (V20-007) surfaced on the form.
        self.assertEqual(lot.wms_lot_state, "available")
        self.assertFalse(lot.wms_is_expired, "a 2027 expiry is not expired")

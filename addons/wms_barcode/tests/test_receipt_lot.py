"""Regression: a scanned lot on Scan Receipt is carried onto the resulting
stock move line, so lot-tracked stock keeps its batch/expiry link.

The lot is captured per scan on the wizard line (``wms.scan.receipt.line``)
but used to be dropped at validate — the receipt then landed lot-tracked stock
with no lot at all. These tests pin the single-lot case and the harder
two-lots-of-one-product case (each scan keeps its own line)."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_receipt_lot")
class TestReceiptLot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "RLOT Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "RLOT Medicine",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "barcode": "RLOTMED001",
                "wms_product_kind": "medicine",
            }
        )
        # _auto_assign_slot raises if the warehouse has no slot/floor, so give
        # it a floor zone to land the receipt in.
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RLOT Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.lot_a = cls.env["stock.lot"].create(
            {"name": "RLOT-A", "product_id": cls.product.id, "company_id": cls.env.company.id}
        )
        cls.lot_b = cls.env["stock.lot"].create(
            {"name": "RLOT-B", "product_id": cls.product.id, "company_id": cls.env.company.id}
        )

    def _wizard(self):
        return self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "qc_passed": True, "storekeeper_id": self.keeper.id}
        )

    def test_single_scanned_lot_lands_on_move_line(self):
        wiz = self._wizard()
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.product.id,
                "quantity": 5.0,
                "lot_id": self.lot_a.id,
            }
        )
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "the receipt should create a picking")
        self.assertEqual(wiz.picking_id.state, "done")
        mls = wiz.picking_id.move_ids.move_line_ids
        self.assertEqual(len(mls), 1, "one scanned line -> one move line")
        self.assertEqual(mls.lot_id, self.lot_a, "the scanned lot must land on the move line")
        self.assertAlmostEqual(mls.quantity, 5.0, places=3)
        # The stock is genuinely on-hand under that lot.
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.product, self.floor, lot_id=self.lot_a
            ),
            5.0,
            places=3,
        )

    def test_two_lots_same_product_keep_separate_move_lines(self):
        wiz = self._wizard()
        Line = self.env["wms.scan.receipt.line"]
        Line.create(
            {
                "wizard_id": wiz.id,
                "product_id": self.product.id,
                "quantity": 3.0,
                "lot_id": self.lot_a.id,
            }
        )
        Line.create(
            {
                "wizard_id": wiz.id,
                "product_id": self.product.id,
                "quantity": 2.0,
                "lot_id": self.lot_b.id,
            }
        )
        wiz.action_validate()
        self.assertEqual(wiz.picking_id.state, "done")
        mls = wiz.picking_id.move_ids.move_line_ids
        by_lot = {ml.lot_id: ml.quantity for ml in mls}
        self.assertIn(self.lot_a, by_lot, "lot A must keep its own move line")
        self.assertIn(self.lot_b, by_lot, "lot B must keep its own move line")
        self.assertAlmostEqual(by_lot[self.lot_a], 3.0, places=3)
        self.assertAlmostEqual(by_lot[self.lot_b], 2.0, places=3)

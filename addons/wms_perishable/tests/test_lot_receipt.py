"""V20-003/004/005 — perishables are lot-tracked from creation, and Scan
Receipt finds-or-creates the lot (never merges; auto-names without a batch)."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLotReceipt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "Lot Receipt Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "LR Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "LR Paracetamol",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "LRMED01",
            }
        )

    def _onhand(self, lot):
        return sum(
            self.env["stock.quant"]
            .search(
                [
                    ("product_id", "=", self.med.id),
                    ("lot_id", "=", lot.id),
                    ("location_id.usage", "=", "internal"),
                ]
            )
            .mapped("quantity")
        )

    def _receipt(self, qty, batch=None, expiry=None, supplier=None):
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.med.id,
                "quantity": qty,
                "location_dest_id": self.floor.id,
                "wms_batch": batch or False,
                "wms_expiry": expiry or False,
                "wms_supplier_id": supplier.id if supplier else False,
            }
        )
        wiz.action_validate()
        return wiz

    def test_perishable_is_lot_tracked_on_create(self):
        self.assertEqual(self.med.tracking, "lot")
        self.assertTrue(self.med.product_tmpl_id.use_expiration_date)

    def test_non_perishable_unchanged(self):
        tool = self.env["product.product"].create(
            {"name": "LR Drill", "type": "consu", "is_storable": True, "wms_product_kind": "tool"}
        )
        self.assertEqual(tool.tracking, "none")

    def test_explicit_batch_creates_lot_with_metadata(self):
        sup = self.env["res.partner"].create({"name": "LR Supplier"})
        self._receipt(100, batch="A101", expiry="2027-12-31", supplier=sup)
        lot = self.env["stock.lot"].search(
            [("product_id", "=", self.med.id), ("name", "=", "A101")], limit=1
        )
        self.assertTrue(lot, "explicit batch must create a named lot")
        self.assertEqual(lot.wms_supplier_id, sup)
        self.assertTrue(lot.expiration_date)
        self.assertEqual(self._onhand(lot), 100)

    def test_no_batch_autonames_lot(self):
        self._receipt(50)
        lots = self.env["stock.lot"].search(
            [("product_id", "=", self.med.id), ("name", "=like", "LOT-%")]
        )
        self.assertTrue(lots, "a no-batch perishable receipt must auto-name a LOT- lot")

    def test_same_batch_never_duplicates(self):
        self._receipt(10, batch="B205", expiry="2027-06-30")
        self._receipt(5, batch="B205", expiry="2027-06-30")
        lots = self.env["stock.lot"].search(
            [("product_id", "=", self.med.id), ("name", "=", "B205")]
        )
        self.assertEqual(len(lots), 1, "same batch must reuse one lot, never duplicate")
        self.assertEqual(self._onhand(lots), 15, "both receipts land on the one B205 lot")

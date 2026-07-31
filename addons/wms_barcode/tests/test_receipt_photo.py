"""Batch 6 — a delivery photo on Scan Receipt (parity with Scan Issue / Damage).
The wizard's photo, when present, is attached to the resulting receipt picking
for the audit trail."""

import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_receipt_photo")
class TestReceiptPhoto(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "RPH Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "RPH Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "RPHTEST001",
                "wms_product_kind": "consumable",
            }
        )
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RPH Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    def test_receipt_photo_field_exists(self):
        self.assertIn("photo", self.env["wms.scan.receipt"]._fields)

    def test_receipt_photo_attached_to_picking(self):
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n")
        wiz = self.env["wms.scan.receipt"].create(
            {
                "warehouse_id": self.wh.id,
                "qc_passed": True,
                "storekeeper_id": self.keeper.id,
                "photo": png,
            }
        )
        self.env["wms.scan.receipt.line"].create(
            {"wizard_id": wiz.id, "product_id": self.product.id, "quantity": 2.0}
        )
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "the receipt should create a picking")
        att = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.picking"),
                ("res_id", "=", wiz.picking_id.id),
                ("name", "like", "receipt-photo-%"),
            ]
        )
        self.assertTrue(att, "the delivery photo should be attached to the receipt")

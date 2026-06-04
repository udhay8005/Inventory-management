"""Critical #2 - receipt line quantity must be positive."""

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_quantity")
class TestReceiptQuantity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({"name": "Receipt Qty Product"})
        # The receipt wizard requires an on-duty storekeeper.
        cls.keeper = cls.env["wms.storekeeper"].create({"name": "Qty Test Keeper"})
        cls.wizard = cls.env["wms.scan.receipt"].create({"storekeeper_id": cls.keeper.id})

    def test_receipt_line_quantity_must_be_positive(self):
        line = self.env["wms.scan.receipt.line"].create(
            {"wizard_id": self.wizard.id, "product_id": self.product.id, "quantity": 1.0}
        )
        for bad in (0, -2):
            with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        "UPDATE wms_scan_receipt_line SET quantity=%s WHERE id=%s",
                        (bad, line.id),
                    )

"""Critical #2 - receipt line quantity must be positive."""

from odoo.exceptions import UserError
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


@tagged("post_install", "-at_install", "wms", "wms_quantity")
class TestIssueQuantity(TransactionCase):
    """D1 + D6(a): Scan Issue must refuse a non-positive quantity with a clear
    message instead of mis-reporting it (a fake 'Planned 0' for zero, or a
    bogus 'STOCK OUT' for a negative), and the empty-plan validate message must
    name the real cause."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "Issue Qty Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Issue Qty Product",
                "type": "consu",
                "is_storable": True,
                "barcode": "ISSQTY001",
                "wms_product_kind": "consumable",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 10.0)

    def _wiz(self, qty, scan="ISSQTY001"):
        return self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": scan,
                "taken_by": "Test Taker",
                "usage_note": "qty integrity test",
                "storekeeper_id": self.keeper.id,
            }
        )

    def test_issue_rejects_non_positive_requested_qty(self):
        for bad in (0.0, -2.0):
            wiz = self._wiz(bad)
            with self.assertRaises(UserError) as cm:
                wiz.action_plan()
            self.assertIn("greater than zero", cm.exception.args[0])
        # the legitimate default of 1 still plans normally against live stock
        wiz = self._wiz(1.0)
        wiz.action_plan()
        self.assertTrue(wiz.plan_line_ids, "a positive qty must still produce a plan")
        self.assertFalse(wiz.short_qty, "10 on hand, asked 1 -> no shortfall")

    def test_validate_empty_plan_message_names_stock(self):
        # nothing scanned -> empty plan -> the message must name the real cause
        wiz = self._wiz(1.0, scan=False)
        with self.assertRaises(UserError) as cm:
            wiz.action_validate()
        self.assertIn("nothing planned to issue", cm.exception.args[0])

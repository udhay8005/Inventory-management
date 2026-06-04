"""Critical #2 - audit counted quantity cannot be negative (zero is valid)."""

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_quantity")
class TestAuditCountedQuantity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({"name": "Audit Qty Product"})
        cls.loc = cls.env.ref("stock.stock_location_stock")
        cls.audit = cls.env["wms.audit"].create({})

    def _line(self):
        return self.env["wms.audit.line"].create(
            {
                "audit_id": self.audit.id,
                "location_id": self.loc.id,
                "product_id": self.product.id,
                "counted_qty": 0.0,
            }
        )

    def test_counted_qty_cannot_be_negative(self):
        line = self._line()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "UPDATE wms_audit_line SET counted_qty=%s WHERE id=%s", (-1, line.id)
                )

    def test_counted_qty_zero_is_allowed(self):
        # Counting zero stock in a slot is valid (an empty slot).
        line = self._line()
        self.assertEqual(line.counted_qty, 0.0)

"""Critical #2 - quantity-integrity constraints (damage / repair).

A DB-level CHECK(quantity > 0) on wms.damage and wms.repair.order blocks the
negative/zero path the audit flagged: a negative-qty damage move ADDS phantom
stock to the source slot. We create a valid record (qty=1) then raw-UPDATE it
to the bad value, so we hit the DB guarantee directly (clean IntegrityError),
mirroring wms_barcode/tests/test_audit_integrity.py.
"""

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_quantity")
class TestRepairDamageQuantity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {"name": "Qty Integrity Product", "is_storable": True}
        )
        cls.loc = cls.env.ref("stock.stock_location_stock")
        # Give the slot real stock so a valid (qty=1) damage passes the
        # source-stock constraint before we raw-UPDATE it to a bad value.
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.loc, 10.0)

    def test_damage_quantity_must_be_positive(self):
        dmg = self.env["wms.damage"].create(
            {"product_id": self.product.id, "source_slot_id": self.loc.id, "quantity": 1.0}
        )
        for bad in (0, -5):
            with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        "UPDATE wms_damage SET quantity=%s WHERE id=%s", (bad, dmg.id)
                    )

    def test_repair_quantity_must_be_positive(self):
        rep = self.env["wms.repair.order"].create({"product_id": self.product.id, "quantity": 1.0})
        for bad in (0, -3):
            with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        "UPDATE wms_repair_order SET quantity=%s WHERE id=%s", (bad, rep.id)
                    )

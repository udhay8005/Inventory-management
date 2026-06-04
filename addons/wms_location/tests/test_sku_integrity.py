"""Critical #3 - product SKU (default_code) uniqueness.

Odoo CE only warns on duplicate internal references; the WMS now enforces a
DB-level UNIQUE(default_code) on product.product so a duplicate SKU (which would
print an ambiguous barcode and break scan resolution) is impossible. Multiple
code-less products are still allowed (Postgres UNIQUE permits many NULLs).
"""

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_sku")
class TestSkuUniqueness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env["product.product"]

    def test_duplicate_sku_rejected(self):
        # No wms_product_kind -> the prefix constraint stays out of the way.
        self.Product.create({"name": "SKU Dup A", "default_code": "SKUDUP-A"})
        b = self.Product.create({"name": "SKU Dup B", "default_code": "SKUDUP-B"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "UPDATE product_product SET default_code=%s WHERE id=%s",
                    ("SKUDUP-A", b.id),
                )

    def test_multiple_null_skus_allowed(self):
        # Two code-less products must coexist (UNIQUE permits many NULLs).
        p1 = self.Product.create({"name": "No SKU 1"})
        p2 = self.Product.create({"name": "No SKU 2"})
        self.assertFalse(p1.default_code)
        self.assertFalse(p2.default_code)

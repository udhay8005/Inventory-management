"""Critical #4 - carton alias barcodes must not collide with product /
location / lot barcodes (a collision shadows the alias in resolve())."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_barcode_collision")
class TestAliasBarcodeCollision(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.target = cls.env["product.product"].create({"name": "Alias Target"})
        cls.with_bc = cls.env["product.product"].create(
            {"name": "Has Barcode", "barcode": "PROD-BC-1"}
        )
        cls.loc = cls.env["stock.location"].create(
            {
                "name": "BC Loc",
                "usage": "internal",
                "location_id": cls.env.ref("stock.stock_location_stock").id,
                "barcode": "LOC-BC-1",
            }
        )
        cls.lot_prod = cls.env["product.product"].create(
            {"name": "Lot Prod", "is_storable": True, "tracking": "lot"}
        )
        cls.lot = cls.env["stock.lot"].create(
            {
                "name": "LOT-BC-1",
                "product_id": cls.lot_prod.id,
                "company_id": cls.env.company.id,
            }
        )

    def _alias(self, barcode):
        return self.env["wms.barcode.alias"].create(
            {"barcode": barcode, "product_id": self.target.id}
        )

    def test_collides_with_product_barcode(self):
        with self.assertRaises(ValidationError):
            self._alias("PROD-BC-1")

    def test_collides_with_location_barcode(self):
        with self.assertRaises(ValidationError):
            self._alias("LOC-BC-1")

    def test_collides_with_lot_name(self):
        with self.assertRaises(ValidationError):
            self._alias("LOT-BC-1")

    def test_unique_alias_is_allowed(self):
        alias = self._alias("CTN-UNIQUE-1")
        self.assertTrue(alias.id)

    def test_units_per_scan_must_be_positive(self):
        """A carton alias multiplier must be > 0. A 0 or negative multiplier
        makes every scan of that carton a silent dead-end on issues and a raw
        IntegrityError on receipts; the CHECK blocks it at write time."""
        for bad in (0, -2):
            with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
                with self.env.cr.savepoint():
                    self.env["wms.barcode.alias"].create(
                        {
                            "barcode": "CTN-UPS-%s" % abs(bad),
                            "product_id": self.target.id,
                            "units_per_scan": bad,
                        }
                    )
                    self.env.cr.flush()
        # a positive multiplier is still accepted
        alias = self.env["wms.barcode.alias"].create(
            {"barcode": "CTN-UPS-24", "product_id": self.target.id, "units_per_scan": 24}
        )
        self.assertTrue(alias.id)

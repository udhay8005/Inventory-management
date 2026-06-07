"""Quick-win D - bulk onboard hardening.

Pre-import validation catches dup SKU / dup barcode / invalid-slot BEFORE any
write hits the DB, so a typo at the 50th row of a 200-row CSV doesn't leave 49
half-saved products behind. New optional columns (SKU, barcode, Category, UoM,
unit cost) feed through to the created template.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_onboard_validation")
class TestOnboardValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "OBV Floor",
                "usage": "internal",
                "location_id": cls.wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        cls.bad_location = cls.env.ref("stock.stock_location_stock")
        # Pre-existing product so we can test "SKU already used".
        cls.existing = cls.env["product.product"].create(
            {
                "name": "OBV Existing",
                "type": "consu",
                "is_storable": True,
                "default_code": "CONS-99001",
                "barcode": "5901234123457",
                "wms_product_kind": "consumable",
            }
        )

    def _wiz(self, lines):
        return self.env["wms.product.onboard"].create({"line_ids": [(0, 0, ln) for ln in lines]})

    def test_duplicate_sku_in_batch_blocks_import(self):
        wiz = self._wiz(
            [
                {
                    "name": "A",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "default_code": "CONS-99500",
                },
                {
                    "name": "B",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "default_code": "CONS-99500",
                },
            ]
        )
        with self.assertRaises(UserError):
            wiz._validate()

    def test_existing_sku_blocks_import(self):
        wiz = self._wiz(
            [
                {
                    "name": "C",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "default_code": "CONS-99001",
                }
            ]
        )
        with self.assertRaises(UserError):
            wiz._validate()

    def test_existing_barcode_blocks_import(self):
        wiz = self._wiz(
            [
                {
                    "name": "D",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "barcode": "5901234123457",
                }
            ]
        )
        with self.assertRaises(UserError):
            wiz._validate()

    def test_invalid_slot_blocks_import(self):
        wiz = self._wiz(
            [
                {
                    "name": "E",
                    "wms_product_kind": "consumable",
                    "initial_qty": 1.0,
                    "location_id": self.bad_location.id,
                }
            ]
        )
        with self.assertRaises(UserError):
            wiz._validate()

    def test_valid_import_writes_new_fields(self):
        Categ = self.env["product.category"].create({"name": "OBV Cat"})
        wiz = self._wiz(
            [
                {
                    "name": "OBV Brand New",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "categ_id": Categ.id,
                    "standard_price": 17.5,
                }
            ]
        )
        wiz._validate()
        wiz._do_onboard()
        p = self.env["product.product"].search([("name", "=", "OBV Brand New")], limit=1)
        self.assertTrue(p, "the import should have created the product")
        self.assertEqual(p.categ_id, Categ, "Category should be applied")
        self.assertAlmostEqual(p.standard_price, 17.5, places=2)

    def test_failed_validation_creates_no_products(self):
        wiz = self._wiz(
            [
                {
                    "name": "OBV Should Not Exist",
                    "wms_product_kind": "consumable",
                    "initial_qty": 0,
                    "default_code": "CONS-99001",  # dup => fails
                }
            ]
        )
        with self.assertRaises(UserError):
            wiz._validate()
        self.assertFalse(
            self.env["product.product"].search([("name", "=", "OBV Should Not Exist")]),
            "no product should be created when validation fails",
        )

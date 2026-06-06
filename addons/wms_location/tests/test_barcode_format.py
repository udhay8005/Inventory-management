"""Maturity: barcode FORMAT validation on create + import. The system already
enforces barcode UNIQUENESS; this adds GS1 check-digit + control-char validation
for operator-typed / imported barcodes, while staying permissive for the
SKU-as-barcode convention (e.g. TOOL-00001)."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_barcode_format")
class TestBarcodeFormat(TransactionCase):
    def test_valid_ean13_accepted(self):
        # 5901234123457 is the GS1 reference (check digit 7).
        p = self.env["product.product"].create({"name": "EAN OK", "barcode": "5901234123457"})
        self.assertEqual(p.barcode, "5901234123457")

    def test_bad_ean13_check_digit_rejected(self):
        # 590123412345 needs check digit 7; 0 is wrong -> rejected.
        with self.assertRaises(ValidationError):
            self.env["product.product"].create({"name": "EAN bad", "barcode": "5901234123450"})

    def test_alphanumeric_sku_barcode_allowed(self):
        # SKU-as-barcode (non-numeric) must stay permissive.
        p = self.env["product.product"].create({"name": "SKU bc", "barcode": "TOOL-00099"})
        self.assertEqual(p.barcode, "TOOL-00099")

"""Critical #4 - location barcodes must be globally unique (NULL-safe),
closing the company_id IS NULL gap in core's UNIQUE(barcode, company_id)."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_barcode_collision")
class TestLocationBarcodeUniqueness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.env.ref("stock.stock_location_stock")

    def _loc(self, name, barcode):
        # company_id=False (NULL) is the exact gap we close: core's
        # UNIQUE(barcode, company_id) treats NULL companies as distinct and
        # does NOT guard duplicates, so our @api.constrains must.
        return self.env["stock.location"].create(
            {
                "name": name,
                "usage": "internal",
                "location_id": self.parent.id,
                "barcode": barcode,
                "company_id": False,
            }
        )

    def test_duplicate_location_barcode_rejected(self):
        self._loc("Loc A", "LOCUNIQ-1")
        with self.assertRaises(ValidationError):
            self._loc("Loc B", "LOCUNIQ-1")

    def test_distinct_barcodes_ok(self):
        a = self._loc("Loc C", "LOCUNIQ-2")
        b = self._loc("Loc D", "LOCUNIQ-3")
        self.assertTrue(a.id and b.id)

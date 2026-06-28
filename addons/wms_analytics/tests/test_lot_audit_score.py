"""Wave 2 #10 — Lot audit / completeness score."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestLotAuditScore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "AUD Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.supplier = cls.env["res.partner"].create({"name": "AUD Supplier"})
        cls.med = cls.env["product.product"].create(
            {
                "name": "AUD Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "AUDMED01",
            }
        )

    def test_bare_autonamed_lot_scores_low(self):
        # Auto-named (LOT-...), no supplier/expiry/stock → only barcode check.
        lot = self.env["stock.lot"].create(
            {"name": "LOT-000999", "product_id": self.med.id, "company_id": self.env.company.id}
        )
        self.assertEqual(lot.wms_audit_band, "low")
        self.assertFalse(lot.wms_audit_batch_ok, "auto-named lot fails the batch check")
        self.assertTrue(lot.wms_audit_barcode_ok, "the lot name is still a scannable barcode")
        self.assertLessEqual(lot.wms_audit_score, 3)

    def test_fully_documented_stocked_lot_scores_high(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "AUD-FULL-1",
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "wms_supplier_id": self.supplier.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=200),
            }
        )
        # Put it in storage and move it so timeline/movement/storage pass.
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 10, lot_id=lot)
        self.assertTrue(lot.wms_audit_batch_ok)
        self.assertTrue(lot.wms_audit_supplier_ok)
        self.assertTrue(lot.wms_audit_expiry_ok)
        self.assertTrue(lot.wms_audit_movement_ok, "live quant counts as movement")
        self.assertTrue(lot.wms_audit_storage_ok, "internal location counts as storage")
        self.assertGreaterEqual(lot.wms_audit_score, 5)

    def test_score_is_seven_checks(self):
        lot = self.env["stock.lot"].create(
            {"name": "AUD-RANGE", "product_id": self.med.id, "company_id": self.env.company.id}
        )
        self.assertGreaterEqual(lot.wms_audit_score, 0)
        self.assertLessEqual(lot.wms_audit_score, 7)
        self.assertEqual(lot.wms_audit_pct, round(100.0 * lot.wms_audit_score / 7.0, 1))

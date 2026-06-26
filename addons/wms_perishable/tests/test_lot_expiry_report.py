"""V20-015 — the per-lot expiry report buckets each batch by its own expiry
(owner thresholds) and totals the value at risk per lot."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLotExpiryReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "LE Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "LE Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "LEMED01",
            }
        )
        cls.med.standard_price = 10.0

    def _seed_lot(self, name, expiry_dt, qty=4):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": expiry_dt,
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, qty, lot_id=lot)
        return lot

    def test_per_lot_expiry_buckets_and_value(self):
        now = fields.Datetime.now()
        lot_exp = self._seed_lot("LE-EXP", now - timedelta(days=10))
        lot_near = self._seed_lot("LE-NEAR", now + timedelta(days=5))
        lot_ok = self._seed_lot("LE-OK", now + timedelta(days=200))
        self.env.flush_all()

        report = self.env["wms.lot.expiry.alert"]
        rows = report.search([("product_id", "=", self.med.id)])
        by_lot = {r.lot_id: r for r in rows}

        self.assertEqual(by_lot[lot_exp].status, "expired", "past expiry -> expired")
        self.assertEqual(by_lot[lot_near].status, "d7", "+5 days -> within 7-day band")
        self.assertEqual(by_lot[lot_ok].status, "ok", "+200 days -> comfortable")
        self.assertEqual(by_lot[lot_exp].on_hand, 4.0)
        self.assertAlmostEqual(
            by_lot[lot_exp].value_at_risk, 40.0, places=2, msg="4 units x 10.0 unit cost"
        )
        self.assertLess(by_lot[lot_exp].days_to_expiry, 0, "expired lot has negative days")

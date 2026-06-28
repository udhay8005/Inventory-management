"""Wave 2 #2 — Expiry Risk Engine: consume-before-expiry banding."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestExpiryRisk(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RISK Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "RISK Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "RISKMED01",
            }
        )

    def _lot(self, name, days):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=days),
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 100, lot_id=lot)
        return lot

    def _forecast(self, daily_avg):
        self.env["wms.forecast"].create(
            {"product_id": self.med.id, "daily_avg": daily_avg, "horizon_days": 30}
        )

    def _risk(self, lot):
        self.env.flush_all()
        rec = self.env["wms.lot.expiry.risk"].search([("lot_id", "=", lot.id)])
        return rec

    def test_no_consumption_near_expiry_is_high(self):
        # daily_avg 0 (nothing being consumed) + 20 days to expiry → HIGH.
        self._forecast(0.0)
        lot = self._lot("RK-NOCONS", 20)
        r = self._risk(lot)
        self.assertEqual(r.risk_band, "high", "stagnant stock near expiry is high risk")

    def test_fast_consumption_is_low(self):
        # 100 on hand, 10/day → 10 days of cover, 200 days to expiry → LOW.
        self._forecast(10.0)
        lot = self._lot("RK-FAST", 200)
        r = self._risk(lot)
        self.assertEqual(r.risk_band, "low", "fast-moving stock is consumed well before expiry")

    def test_surplus_that_outlives_expiry_is_high_or_critical(self):
        # 100 on hand, 1/day → 100 days of cover, only 30 days to expiry → will
        # expire before consumed: high; cover >= 2x life → critical.
        self._forecast(1.0)
        lot = self._lot("RK-SURPLUS", 30)
        r = self._risk(lot)
        self.assertIn(r.risk_band, ("high", "critical"), "unconsumable surplus is high/critical")
        self.assertGreaterEqual(r.days_of_cover, 99.0)

    def test_expired_is_critical(self):
        self._forecast(5.0)
        lot = self._lot("RK-EXP", -3)
        r = self._risk(lot)
        self.assertEqual(r.risk_band, "critical", "already-expired stock is critical")

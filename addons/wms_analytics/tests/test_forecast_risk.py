"""Wave 2 #3 — AI Forecast: weekly demand + overstock/understock risk."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestForecastRisk(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "FCST Risk Product",
                "type": "consu",
                "is_storable": True,
            }
        )

    def _forecast(self, **vals):
        defaults = {
            "product_id": self.product.id,
            "horizon_days": 30,
            "daily_avg": 0.0,
            "on_hand": 0.0,
            "predicted_qty": 0.0,
            "reorder_qty": 0.0,
            "safety_stock": 0.0,
            "lead_time_days": 0,
            "velocity_class": "normal",
        }
        defaults.update(vals)
        # One forecast row per product (UNIQUE constraint): give each call its
        # own product so independent scenarios don't collide.
        if "product_id" not in vals:
            p = self.env["product.product"].create(
                {"name": "FCST P", "type": "consu", "is_storable": True}
            )
            defaults["product_id"] = p.id
        return self.env["wms.forecast"].create(defaults)

    def test_weekly_avg_is_daily_times_seven(self):
        f = self._forecast(daily_avg=3.0)
        self.assertAlmostEqual(f.weekly_avg, 21.0)

    def test_weekly_avg_zero_when_no_consumption(self):
        f = self._forecast(daily_avg=0.0)
        self.assertEqual(f.weekly_avg, 0.0)

    def test_dead_stock_with_on_hand_is_high_overstock(self):
        f = self._forecast(velocity_class="dead", on_hand=50.0, daily_avg=0.0)
        self.assertEqual(f.overstock_risk, "high")

    def test_many_months_cover_is_high_overstock(self):
        # 1/day, 300 on hand → 10 months of cover → high overstock.
        f = self._forecast(daily_avg=1.0, on_hand=300.0, velocity_class="slow")
        self.assertEqual(f.overstock_risk, "high")

    def test_balanced_stock_has_no_overstock(self):
        # 5/day over a 30-day horizon = 150 demand; 100 on hand ~0.66 months.
        f = self._forecast(daily_avg=5.0, on_hand=100.0, velocity_class="fast")
        self.assertEqual(f.overstock_risk, "none")

    def test_below_safety_stock_is_high_understock(self):
        f = self._forecast(daily_avg=2.0, on_hand=5.0, safety_stock=20.0)
        self.assertEqual(f.understock_risk, "high")

    def test_below_lead_time_demand_is_high_understock(self):
        # 4/day, 10-day lead → need 40 to cover lead; only 10 on hand.
        f = self._forecast(daily_avg=4.0, on_hand=10.0, lead_time_days=10)
        self.assertEqual(f.understock_risk, "high")

    def test_reorder_suggested_is_at_least_medium_understock(self):
        # Comfortable on hand but engine flagged a reorder → early warning.
        f = self._forecast(
            daily_avg=1.0,
            on_hand=200.0,
            lead_time_days=5,
            reorder_qty=10.0,
            safety_stock=0.0,
        )
        self.assertEqual(f.understock_risk, "medium")

    def test_well_stocked_has_no_understock(self):
        f = self._forecast(
            daily_avg=2.0,
            on_hand=500.0,
            lead_time_days=7,
            safety_stock=10.0,
            reorder_qty=0.0,
        )
        self.assertEqual(f.understock_risk, "none")

    def test_recompute_on_source_change(self):
        # Stored + @api.depends: editing on_hand re-runs the risk compute.
        f = self._forecast(daily_avg=2.0, on_hand=500.0, safety_stock=10.0)
        self.assertEqual(f.understock_risk, "none")
        f.write({"on_hand": 1.0})
        self.env.flush_all()
        self.assertEqual(f.understock_risk, "high")

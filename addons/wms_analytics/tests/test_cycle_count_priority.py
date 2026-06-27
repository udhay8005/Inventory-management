"""Wave 2 #14 — Cycle Count Intelligence: risk-ranked count order."""

from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestCycleCountPriority(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Manager rights — audit decision methods are manager-gated, and we
        # write audit lines / quants while seeding.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]

        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id

        # Two storage floors: one stale + previously-wrong, one freshly counted
        # and clean.
        cls.stale = cls.env["stock.location"].create(
            {
                "name": "CCP Stale Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.fresh = cls.env["stock.location"].create(
            {
                "name": "CCP Fresh Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

        # A plain consumable so no auto lot-tracking complicates the quant.
        cls.prod = cls.env["product.product"].create(
            {
                "name": "CCP Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "CCPWIDGET01",
            }
        )

        # Stock in both slots so they are real storage with on-hand.
        cls.env["stock.quant"]._update_available_quantity(cls.prod, cls.stale, 50)
        cls.env["stock.quant"]._update_available_quantity(cls.prod, cls.fresh, 50)

        # Age signal: stamp the stale slot's quant as counted ~120 days ago and
        # the fresh slot's quant as counted today, then let the stored
        # wms_last_counted compute from last_count_date.
        old = date.today() - timedelta(days=120)
        cls.env["stock.quant"].search(
            [("location_id", "=", cls.stale.id), ("product_id", "=", cls.prod.id)]
        ).write({"last_count_date": old})
        cls.env["stock.quant"].search(
            [("location_id", "=", cls.fresh.id), ("product_id", "=", cls.prod.id)]
        ).write({"last_count_date": date.today()})

        # Accuracy signal: a past audit with a variance line at the stale slot.
        audit = cls.env["wms.audit"].create({})
        cls.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": cls.stale.id,
                "product_id": cls.prod.id,
                "expected_qty": 50.0,
                "counted_qty": 42.0,  # variance = -8 → counts as a mismatch
            }
        )

        # Refresh the stored count-age so the SQL view's inline delta is current.
        slots = cls.stale | cls.fresh
        slots._compute_wms_last_counted()
        slots.flush_recordset(["wms_last_counted"])
        cls.env.flush_all()

    def _row(self, loc):
        return self.env["wms.cycle.count.priority"].search([("location_id", "=", loc.id)])

    def test_stale_with_variance_outranks_fresh_clean(self):
        stale = self._row(self.stale)
        fresh = self._row(self.fresh)
        self.assertTrue(stale, "stale slot should appear in the priority view")
        self.assertTrue(fresh, "fresh slot should appear in the priority view")
        self.assertGreater(
            stale.priority_score,
            fresh.priority_score,
            "an old, previously-mismatched slot must rank above a freshly-counted clean one",
        )

    def test_stale_slot_signals(self):
        stale = self._row(self.stale)
        self.assertGreaterEqual(stale.days_since_count, 90, "stale slot is ~120 days overdue")
        self.assertGreaterEqual(stale.mismatch_count, 1, "stale slot has one past variance line")
        self.assertGreater(stale.age_points, 0, "age must contribute points")
        self.assertGreater(stale.mismatch_points, 0, "past variance must contribute points")

    def test_fresh_clean_slot_is_low_band(self):
        fresh = self._row(self.fresh)
        self.assertEqual(fresh.mismatch_count, 0, "fresh slot has no audit variances")
        self.assertEqual(fresh.priority_band, "low", "freshly-counted clean slot is low priority")

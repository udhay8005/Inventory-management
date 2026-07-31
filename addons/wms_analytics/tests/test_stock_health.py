"""Wave 2 — Stock Health Score: five-bucket precedence classification."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestStockHealth(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.stock = cls.wh.lot_stock_id
        # A dedicated internal floor so this test's quants are isolated and
        # countable; the view aggregates per company, so we assert deltas.
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "HEALTH Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "HEALTH Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "HEALTHMED01",
            }
        )

    def _lot(self, name, days_to_expiry, qty, state="available"):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=days_to_expiry),
                "wms_lot_state": state,
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, qty, lot_id=lot)
        return lot

    def _row(self):
        self.env.flush_all()
        return self.env["wms.stock.health"].search([("company_id", "=", self.company.id)])

    def test_buckets_and_score(self):
        # Seed one lot per bucket, distinct quantities so each contribution is
        # individually identifiable in the aggregate.
        baseline = self._row()
        base_total = baseline.total_qty if baseline else 0.0
        base_healthy = baseline.healthy_qty if baseline else 0.0
        base_near = baseline.near_qty if baseline else 0.0
        base_expired = baseline.expired_qty if baseline else 0.0
        base_quar = baseline.quarantine_qty if baseline else 0.0
        base_recall = baseline.recall_qty if baseline else 0.0

        self._lot("H-HEALTHY", 200, 10, state="available")  # far expiry -> healthy
        self._lot("H-NEAR", 10, 20, state="available")  # within 30d -> near
        self._lot("H-EXPIRED", -5, 30, state="available")  # past -> expired
        self._lot("H-QUAR", 200, 40, state="quarantine")  # state wins -> quarantine
        self._lot("H-RECALL", 200, 50, state="recalled")  # state wins -> recall

        row = self._row()
        self.assertTrue(row, "a health row must exist for the company")
        self.assertEqual(len(row), 1, "exactly one row per company")

        self.assertAlmostEqual(row.healthy_qty - base_healthy, 10.0, places=2)
        self.assertAlmostEqual(row.near_qty - base_near, 20.0, places=2)
        self.assertAlmostEqual(row.expired_qty - base_expired, 30.0, places=2)
        self.assertAlmostEqual(row.quarantine_qty - base_quar, 40.0, places=2)
        self.assertAlmostEqual(row.recall_qty - base_recall, 50.0, places=2)
        self.assertAlmostEqual(row.total_qty - base_total, 150.0, places=2)

    def test_precedence_recall_over_expiry(self):
        # A recalled lot that is ALSO expired must count as recall, never expired
        # (Recall > ... > Expired precedence).
        before = self._row()
        base_recall = before.recall_qty if before else 0.0
        base_expired = before.expired_qty if before else 0.0

        self._lot("H-RECALL-EXP", -10, 7, state="recalled")

        row = self._row()
        self.assertAlmostEqual(row.recall_qty - base_recall, 7.0, places=2)
        self.assertAlmostEqual(row.expired_qty - base_expired, 0.0, places=2)

    def test_score_is_healthy_pct(self):
        row = self._row()
        if row and row.total_qty:
            self.assertAlmostEqual(row.overall_score, row.healthy_pct, places=4)
            self.assertAlmostEqual(
                row.healthy_pct, 100.0 * row.healthy_qty / row.total_qty, places=4
            )

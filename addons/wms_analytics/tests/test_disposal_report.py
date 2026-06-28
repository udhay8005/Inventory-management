"""Wave 2 — Disposal / loss analytics: damage + destroyed-lot union view."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestDisposalReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "DISP Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.prod = cls.env["product.product"].create(
            {
                "name": "DISP Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "DISPMED01",
                "standard_price": 7.0,
            }
        )

    def _disposal_rows(self, product):
        self.env.flush_all()
        Report = self.env["wms.disposal.report"]
        return Report.search([("product_id", "=", product.id)])

    def test_confirmed_damage_appears_with_value(self):
        # Seed a confirmed damage directly (state + frozen value snapshot),
        # bypassing the picking machinery to keep the test deterministic.
        self.env["wms.damage"].create(
            {
                "product_id": self.prod.id,
                "quantity": 4.0,
                "source_slot_id": self.floor.id,
                "reason": "broken",
                "state": "confirmed",
                "damage_value": 28.0,
            }
        )
        rows = self._disposal_rows(self.prod)
        damage_rows = rows.filtered(lambda r: r.source == "damage")
        self.assertEqual(len(damage_rows), 1, "confirmed damage should produce exactly one row")
        row = damage_rows[0]
        self.assertEqual(row.reason, "Broken")
        self.assertEqual(row.quantity, 4.0)
        self.assertEqual(row.disposal_value, 28.0)
        self.assertTrue(row.month, "month bucket must be populated")
        self.assertEqual(row.month.day, 1, "month must be truncated to first of month")

    def test_draft_damage_excluded(self):
        # A draft damage re-validates free stock at the slot, so seed some first.
        seed_lot = self.env["stock.lot"].create(
            {"name": "DISP-SEED", "product_id": self.prod.id, "company_id": self.env.company.id}
        )
        self.env["stock.quant"]._update_available_quantity(
            self.prod, self.floor, 5, lot_id=seed_lot
        )
        self.env["wms.damage"].create(
            {
                "product_id": self.prod.id,
                "quantity": 2.0,
                "source_slot_id": self.floor.id,
                "reason": "broken",
                "state": "draft",
            }
        )
        rows = self._disposal_rows(self.prod)
        self.assertFalse(
            rows.filtered(lambda r: r.source == "damage"),
            "draft damage must not appear in the disposal report",
        )

    def test_destroyed_lot_valued_by_onhand_cost(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "DISP-DEAD",
                "product_id": self.prod.id,
                "company_id": self.env.company.id,
                "wms_lot_state": "destroyed",
            }
        )
        # 5 on hand x 7.0 unit cost -> 35.0 disposal value.
        self.env["stock.quant"]._update_available_quantity(self.prod, self.floor, 5, lot_id=lot)
        rows = self._disposal_rows(self.prod)
        destroyed = rows.filtered(lambda r: r.source == "destroyed")
        self.assertEqual(len(destroyed), 1, "destroyed lot should produce exactly one row")
        row = destroyed[0]
        self.assertEqual(row.reason, "Destroyed lot")
        self.assertEqual(row.quantity, 5.0)
        self.assertAlmostEqual(row.disposal_value, 35.0, places=2)

    def test_available_lot_excluded(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "DISP-LIVE",
                "product_id": self.prod.id,
                "company_id": self.env.company.id,
                "wms_lot_state": "available",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.prod, self.floor, 9, lot_id=lot)
        rows = self._disposal_rows(self.prod)
        self.assertFalse(
            rows.filtered(lambda r: r.source == "destroyed"),
            "an available (non-destroyed) lot must not appear as a disposal",
        )

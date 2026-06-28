"""V20-011 — expired lots are kept out of the Scan Issue plan (so a perishable
issue can't plan stock that would then fail to reserve), the shortfall explains
the expired stock on hand, and a manager override can still issue expired."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestExpiredBlock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "EB Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "EB Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "EB Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "EBMED01",
            }
        )

    def _lot(self, name, expiry):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": expiry,
            }
        )

    def _seed(self, lot, qty):
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, qty, lot_id=lot)

    def _plan(self, qty, ctx=None):
        loc = self.env["stock.location"]
        if ctx:
            loc = loc.with_context(**ctx)
        return loc.find_oldest_quants_for_product(
            self.med.id, qty, parent_location_id=self.stock.id
        )

    def test_expired_lot_excluded_from_plan(self):
        expired = self._lot("EB-EXP", "2020-01-01 00:00:00")
        valid = self._lot("EB-OK", "2027-12-31 00:00:00")
        self._seed(expired, 5)
        self._seed(valid, 5)
        plan, missing = self._plan(5)
        planned_lots = {q.lot_id for q, _take in plan}
        self.assertNotIn(expired, planned_lots, "expired lot must never be planned for issue")
        self.assertIn(valid, planned_lots)
        self.assertEqual(missing, 0)

    def test_valid_stock_fully_used_despite_expired_being_earliest(self):
        # The expired lot expires earliest (FEFO would pick it first), but it is
        # excluded; the valid lot alone covers the order. A broken post-filter
        # would take from the expired lot first and under-allocate — this proves
        # the planner is correctly re-implemented (exclude before allocating).
        self._seed(self._lot("EB-EXP2", "2020-01-01 00:00:00"), 8)
        valid = self._lot("EB-OK2", "2027-12-31 00:00:00")
        self._seed(valid, 10)
        plan, missing = self._plan(10)
        self.assertEqual(missing, 0, "the valid lot alone covers the full order")
        self.assertEqual(sum(take for _q, take in plan), 10)
        self.assertTrue(all(q.lot_id == valid for q, _take in plan), "all drawn from the valid lot")

    def test_manager_override_includes_expired(self):
        expired = self._lot("EB-OV", "2020-01-01 00:00:00")
        self._seed(expired, 5)
        plan, missing = self._plan(5, ctx={"wms_allow_expired_removal": True})
        self.assertEqual(missing, 0, "the override lets a manager issue expired stock")
        self.assertTrue(any(q.lot_id == expired for q, _take in plan))

    def test_shortfall_feedback_explains_expired(self):
        self._seed(self._lot("EB-SF", "2020-01-01 00:00:00"), 5)
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": self.med.barcode,
                "requested_qty": 3,
                "storekeeper_id": self.keeper.id,
                "taken_by": "EB Tester",
                "ordered_by": "EB Manager",
                "usage_note": "expired test",
            }
        )
        wiz.action_plan()
        self.assertIn("EXPIRED", wiz.feedback, "shortfall must explain expired stock on hand")

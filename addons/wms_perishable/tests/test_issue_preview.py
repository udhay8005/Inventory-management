"""V20-010 — Scan Issue plan shows the batch each FEFO line draws from, that
batch's own expiry, the resulting balance, and earliest-expiry-first feedback."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestIssuePreview(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "IP Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "IP Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "IP Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "IPMED01",
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

    def _plan(self, qty):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": self.med.barcode,
                "requested_qty": qty,
                "storekeeper_id": self.keeper.id,
                "taken_by": "IP Tester",
                "ordered_by": "IP Manager",
                "usage_note": "preview test",
            }
        )
        wiz.action_plan()
        return wiz

    def test_plan_line_carries_lot_and_per_lot_expiry(self):
        lot_early = self._lot("IP-EARLY", "2027-03-31 00:00:00")
        lot_late = self._lot("IP-LATE", "2027-09-30 00:00:00")
        self.env["stock.quant"]._update_available_quantity(
            self.med, self.floor, 10, lot_id=lot_late
        )
        self.env["stock.quant"]._update_available_quantity(
            self.med, self.floor, 10, lot_id=lot_early
        )
        wiz = self._plan(5)
        first = wiz.plan_line_ids[0]
        self.assertEqual(
            first.lot_id, lot_early, "FEFO line must draw from the earliest-expiry lot"
        )
        self.assertEqual(str(first.expiry_date), "2027-03-31", "line shows the LOT's own expiry")

    def test_resulting_balance(self):
        lot = self._lot("IP-RB", "2027-05-31 00:00:00")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 10, lot_id=lot)
        wiz = self._plan(4)
        line = wiz.plan_line_ids[0]
        self.assertEqual(line.take, 4.0)
        self.assertEqual(line.resulting_balance, 6.0, "10 available - 4 taken = 6 left")

    def test_feedback_says_earliest_expiry_for_perishable(self):
        lot = self._lot("IP-FB", "2027-05-31 00:00:00")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 10, lot_id=lot)
        wiz = self._plan(3)
        self.assertIn("earliest expiry first", wiz.feedback)
        self.assertIn("after this issue", wiz.feedback)

    def test_non_perishable_feedback_unchanged(self):
        tool = self.env["product.product"].create(
            {
                "name": "IP Drill",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "tool",
                "barcode": "IPTOOL01",
            }
        )
        self.env["stock.quant"]._update_available_quantity(tool, self.floor, 10)
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": tool.barcode,
                "requested_qty": 3,
                "storekeeper_id": self.keeper.id,
                "taken_by": "IP Tester",
                "ordered_by": "IP Manager",
                "usage_note": "preview test",
            }
        )
        wiz.action_plan()
        self.assertIn("oldest stock first", wiz.feedback)
        self.assertNotIn("earliest expiry", wiz.feedback)

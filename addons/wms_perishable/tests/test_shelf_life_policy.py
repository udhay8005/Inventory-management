"""V20-022 — per-kind shelf-life policy (spec §2.8): per-kind / per-product
minimum shelf life at receipt and at issue, with a manager override at each gate.

Covers the resolver precedence (product override > kind policy > global), the
per-kind receipt guard, and the new short-dated-at-issue guard."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestShelfLifePolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "SLP Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "SLP Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        # medicine: seeded policy = total 730 / receive 180 / issue 60
        cls.med = cls.env["product.product"].create(
            {
                "name": "SLP Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "SLPMED01",
            }
        )
        # feed: seeded policy = total 90 / receive 30 / issue 7
        cls.feed = cls.env["product.product"].create(
            {
                "name": "SLP Feed",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "feed",
                "barcode": "SLPFEED01",
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "SLP Manager",
                "login": "slp_manager",
                "group_ids": [(6, 0, [cls.env.ref("wms_location.group_wms_manager").id])],
            }
        )
        cls.clerk = cls.env["res.users"].create(
            {
                "name": "SLP Clerk",
                "login": "slp_clerk",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("wms_location.group_wms_can_scan_issue").id,
                            cls.env.ref("wms_location.group_wms_can_scan_receive").id,
                        ],
                    )
                ],
            }
        )

    # ---- resolver precedence -------------------------------------------------
    def test_resolver_uses_kind_policy(self):
        vals = self.med.product_tmpl_id._wms_resolve_shelf_life()
        self.assertEqual(vals["min_receive"], 180, "medicine kind policy min-receive")
        self.assertEqual(vals["min_issue"], 60, "medicine kind policy min-issue")
        self.assertEqual(vals["total"], 730, "medicine kind policy total")

    def test_product_override_beats_kind(self):
        self.med.product_tmpl_id.write(
            {"wms_min_receive_life_days": 10, "wms_min_issue_life_days": 5}
        )
        vals = self.med.product_tmpl_id._wms_resolve_shelf_life()
        self.assertEqual(vals["min_receive"], 10, "product override wins for receive")
        self.assertEqual(vals["min_issue"], 5, "product override wins for issue")

    def test_global_fallback_when_no_policy(self):
        # 'tool' is not perishable and has no policy row → global fallback (60/0).
        tool = self.env["product.product"].create(
            {"name": "SLP Tool", "type": "consu", "is_storable": True, "wms_product_kind": "tool"}
        )
        vals = tool.product_tmpl_id._wms_resolve_shelf_life()
        self.assertEqual(vals["min_receive"], 60, "global receive fallback")
        self.assertEqual(vals["min_issue"], 0, "global issue fallback (disabled)")

    # ---- receipt guard is per-kind ------------------------------------------
    def _receipt(self, product, days, batch):
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": product.id,
                "quantity": 10,
                "location_dest_id": self.floor.id,
                "wms_batch": batch,
                "wms_expiry": fields.Date.today() + timedelta(days=days),
            }
        )
        return wiz

    def test_feed_receive_threshold_is_30_not_60(self):
        # 45 days left: blocked under the old global 60, but feed's policy is 30,
        # so it must now RECEIVE fine — proves the guard is per-kind.
        wiz = self._receipt(self.feed, days=45, batch="FEED-45")
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "feed (min-receive 30) accepts 45-day stock")

    def test_medicine_receive_threshold_is_180(self):
        # 100 days left: fine under the old global 60, but medicine's policy is
        # 180, so it must now be BLOCKED — proves the guard tightened per-kind.
        wiz = self._receipt(self.med, days=100, batch="MED-100")
        with self.assertRaises(UserError):
            wiz.action_validate()
        # A manager can still accept it.
        wiz.with_user(self.manager).action_receive_short_dated_override()
        self.assertTrue(wiz.picking_id, "manager accepts short-dated medicine receipt")

    # ---- short-dated-at-issue guard -----------------------------------------
    def _issue(self, product, qty=3):
        return self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": product.barcode,
                "requested_qty": qty,
                "storekeeper_id": self.keeper.id,
                "taken_by": "SLP Taker",
                "usage_note": "shelf-life issue test",
            }
        )

    def _stock_lot(self, product, name, days):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": product.id,
                "company_id": self.env.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=days),
            }
        )
        self.env["stock.quant"]._update_available_quantity(product, self.floor, 10, lot_id=lot)
        return lot

    def test_short_dated_issue_blocked_then_manager_override(self):
        # medicine min-issue = 60; a lot 30 days from expiry is short-dated at
        # issue (but not expired) → blocked for a clerk, allowed by a manager.
        self._stock_lot(self.med, "MED-ISS-30", days=30)
        wiz = self._issue(self.med)
        wiz.action_plan()
        self.assertTrue(wiz.wms_has_short_dated_issue, "plan flags short-dated-at-issue")
        with self.assertRaises(UserError):
            wiz.action_validate()
        wiz.with_user(self.manager).action_override_short_dated_issue()
        self.assertTrue(wiz.picking_id, "manager approves the short-dated issue")
        self.assertIn("SHORT-DATED ISSUE", wiz.usage_note, "override stamped on audit note")

    def test_healthy_dated_issue_passes(self):
        # medicine min-issue = 60; a lot 400 days out is fine → issues directly.
        self._stock_lot(self.med, "MED-ISS-400", days=400)
        wiz = self._issue(self.med)
        wiz.action_plan()
        self.assertFalse(wiz.wms_has_short_dated_issue, "healthy stock not flagged")
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "healthy-dated issue validates without override")

    def test_non_manager_cannot_override_short_dated_issue(self):
        self._stock_lot(self.med, "MED-ISS-NO", days=30)
        wiz = self._issue(self.med)
        wiz.action_plan()
        with self.assertRaises(UserError):
            wiz.with_user(self.clerk).action_override_short_dated_issue()

"""V20-011b — a Manager (and only a Manager) can override the expiry block and
issue expired stock; the override is stamped onto the audit trail."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestManagerOverride(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "MO Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "MO Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "MO Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "MOMED01",
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "MO Manager",
                "login": "mo_manager",
                "group_ids": [(6, 0, [cls.env.ref("wms_location.group_wms_manager").id])],
            }
        )
        cls.clerk = cls.env["res.users"].create(
            {
                "name": "MO Clerk",
                "login": "mo_clerk",
                "group_ids": [(6, 0, [cls.env.ref("wms_location.group_wms_can_scan_issue").id])],
            }
        )

    def _expired_lot(self, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2020-01-01 00:00:00",
            }
        )

    def _wizard(self):
        return self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "last_scan": self.med.barcode,
                "requested_qty": 3,
                "storekeeper_id": self.keeper.id,
                "taken_by": "MO Taker",
                "ordered_by": "MO Orderer",
                "usage_note": "override test",
            }
        )

    def _on_hand(self, lot):
        return self.env["stock.quant"]._get_available_quantity(self.med, self.floor, lot_id=lot)

    def test_blocked_plan_flags_expired_shortfall(self):
        self.env["stock.quant"]._update_available_quantity(
            self.med, self.floor, 5, lot_id=self._expired_lot("MO-FLAG")
        )
        wiz = self._wizard()
        wiz.action_plan()
        self.assertTrue(wiz.short_qty, "expired-only stock leaves the plan short")
        self.assertTrue(wiz.wms_has_expired_shortfall, "override affordance must be flagged")

    def test_manager_can_override_and_issue_expired(self):
        lot = self._expired_lot("MO-OK")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        wiz = self._wizard()
        wiz.with_user(self.manager).action_override_expired_issue()
        self.assertTrue(wiz.picking_id, "the override issues the stock (picking created)")
        self.assertEqual(self._on_hand(lot), 2.0, "3 of the 5 expired units were issued")
        self.assertIn(
            "EXPIRED-STOCK OVERRIDE", wiz.usage_note, "the override is stamped on the audit note"
        )

    def test_non_manager_cannot_override(self):
        self.env["stock.quant"]._update_available_quantity(
            self.med, self.floor, 5, lot_id=self._expired_lot("MO-NO")
        )
        wiz = self._wizard()
        with self.assertRaises(UserError):
            wiz.with_user(self.clerk).action_override_expired_issue()

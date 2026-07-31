"""V20-013 — recall freezes a lot (un-issuable), cancels its open reservations,
and release restores it. Manager-gated."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestRecall(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.customers = cls.env.ref("stock.stock_location_customers")
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RC Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "RC Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "RCMED01",
            }
        )
        # The acting test user must be a manager to recall/release.
        cls.env.user.write({"group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)]})
        cls.clerk = cls.env["res.users"].create(
            {
                "name": "RC Clerk",
                "login": "rc_clerk",
                "group_ids": [(4, cls.env.ref("wms_location.group_wms_can_scan_issue").id)],
            }
        )

    def _lot(self, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )

    def _recall(self, lot):
        return self.env["wms.lot.recall"].create(
            {"mode": "manual", "reason": "Contamination notice", "lot_ids": [(6, 0, lot.ids)]}
        )

    def _plan(self, qty):
        return self.env["stock.location"].find_oldest_quants_for_product(
            self.med.id, qty, parent_location_id=self.stock.id
        )

    def test_recall_freezes_and_excludes_from_issue(self):
        lot = self._lot("RC-A")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        recall = self._recall(lot)
        recall.action_recall()
        self.assertEqual(lot.wms_lot_state, "recalled")
        self.assertEqual(recall.state, "active")
        plan, missing = self._plan(3)
        self.assertEqual(plan, [], "a recalled lot must be excluded from the issue plan")
        self.assertEqual(missing, 3)

    def test_recall_cancels_open_reservation(self):
        lot = self._lot("RC-RES")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 10, lot_id=lot)
        pick = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh.out_type_id.id,
                "location_id": self.floor.id,
                "location_dest_id": self.customers.id,
            }
        )
        self.env["stock.move"].create(
            {
                "description_picking": "reserve",
                "product_id": self.med.id,
                "product_uom_qty": 5.0,
                "product_uom": self.med.uom_id.id,
                "picking_id": pick.id,
                "location_id": self.floor.id,
                "location_dest_id": self.customers.id,
            }
        )
        pick.action_confirm()
        pick.action_assign()
        self.assertEqual(pick.move_ids.state, "assigned", "the move reserved the lot")
        recall = self._recall(lot)
        recall.action_recall()
        self.assertNotEqual(pick.move_ids.state, "assigned", "recall must cancel the reservation")
        self.assertGreaterEqual(recall.unreserved_count, 1)

    def test_release_restores_issuable(self):
        lot = self._lot("RC-REL")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        recall = self._recall(lot)
        recall.action_recall()
        self.assertEqual(self._plan(3)[0], [], "recalled -> excluded")
        recall.action_release()
        self.assertEqual(lot.wms_lot_state, "available")
        self.assertEqual(recall.state, "released")
        plan, missing = self._plan(3)
        self.assertTrue(plan, "released lot is issuable again")
        self.assertEqual(missing, 0)

    def test_non_manager_cannot_recall(self):
        lot = self._lot("RC-NM")
        recall = self._recall(lot)
        with self.assertRaises(UserError):
            recall.with_user(self.clerk).action_recall()

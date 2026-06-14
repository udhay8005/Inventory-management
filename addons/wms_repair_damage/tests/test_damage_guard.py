"""Chunk 4 (§3B): a confirmed damage is frozen against keeper edits (the loss
is recorded and the stock has moved), while the keeper's normal file -> confirm
flow and the linking of a repair order still work, and a manager can still
correct it."""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_damage_guard")
class TestDamageFinalisedWriteGuard(TransactionCase):
    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "group_ids": [(6, 0, [self.env.ref(xmlid).id])]}
        )

    def setUp(self):
        super().setUp()
        self.keeper = self._user("wms_location.group_wms_can_file_damage", "dg_keeper")
        self.mgr = self._user("wms_location.group_wms_manager", "dg_mgr")
        wh = self.env["stock.warehouse"].search([], limit=1)
        self.floor = self.env["stock.location"].create(
            {
                "name": "DG Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        self.product = self.env["product.product"].create(
            {
                "name": "DG Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "tool",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.product, self.floor, 5.0)
        self.roster = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "DG Roster"})

    def _confirmed_damage(self):
        dmg = self.env["wms.damage"].create(
            {
                "product_id": self.product.id,
                "quantity": 2.0,
                "source_slot_id": self.floor.id,
                "reason": "broken",
                "wms_reported_by": "R",
                "wms_authorized_by": "A",
                "wms_storekeeper_id": self.roster.id,
            }
        )
        dmg.action_confirm()  # draft -> confirmed (single write, allowed)
        self.assertEqual(dmg.state, "confirmed")
        return dmg

    def test_confirmed_damage_frozen_for_keeper(self):
        dmg = self._confirmed_damage()
        # A keeper cannot revise a confirmed damage's business fields.
        with self.assertRaises(AccessError):
            dmg.with_user(self.keeper).write({"quantity": 99.0})
        # ... but may still LINK a repair order (whitelisted field) - the loss
        # stays recorded, the item just routes to repair.
        action = dmg.with_user(self.keeper).action_create_repair_order()
        self.assertTrue(
            dmg.repair_order_id, "keeper may link a repair order from a confirmed damage"
        )
        self.assertEqual(action.get("res_model"), "wms.repair.order")
        # A manager can still correct the record.
        dmg.with_user(self.mgr).write({"quantity": 3.0})
        self.assertEqual(dmg.quantity, 3.0)

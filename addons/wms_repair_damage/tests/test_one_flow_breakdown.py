# -*- coding: utf-8 -*-
"""UAT R3 fixes in wms_repair_damage:

  * one-flow damage->repair: a single button confirms the damage, creates
    the linked repair order and (with repair rights) starts it;
  * the product form's stock breakdown splits internal on-hand into
    on-shelf / out-in-use / damaged / under-repair, so the operator can see
    WHERE a shrinking count went.
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_uat_r3")
class TestOneFlowAndBreakdown(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "R3-DMG-SLOT",
                "usage": "internal",
                "location_id": cls.warehouse.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        cls.keeper = cls.env["wms.storekeeper"].create({"name": "R3 Keeper"})
        cls.tool = cls.env["product.template"].create(
            {"name": "R3 One-Flow Drill", "wms_product_kind": "tool"}
        )
        cls.product = cls.tool.product_variant_id
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.slot, 5)

    def _damage(self, qty=1):
        return self.env["wms.damage"].create(
            {
                "product_id": self.product.id,
                "quantity": qty,
                "source_slot_id": self.slot.id,
                "reason": "broken",
                "wms_reported_by": "Tester",
                "wms_authorized_by": "Manager",
                "wms_storekeeper_id": self.keeper.id,
            }
        )

    def test_one_flow_confirm_and_repair(self):
        """One click: damage confirmed + repair order created and started
        (test env user is admin, who has manager rights)."""
        dmg = self._damage()
        dmg.action_confirm_and_repair()
        self.assertEqual(dmg.state, "confirmed", "damage must be confirmed")
        self.assertTrue(dmg.repair_order_id, "repair order must be created")
        self.assertEqual(
            dmg.repair_order_id.state,
            "in_repair",
            "with repair rights the one-flow must also START the repair",
        )

    def test_one_flow_idempotent_on_confirmed(self):
        """Pressing the one-flow on an already-confirmed damage just creates /
        opens the repair without re-confirming (no double stock move)."""
        dmg = self._damage()
        dmg.action_confirm()
        damage_loc_qty = self._qty_at_damage()
        dmg.action_confirm_and_repair()
        self.assertTrue(dmg.repair_order_id)
        self.assertLessEqual(
            self._qty_at_damage(),
            damage_loc_qty,
            "re-running the one-flow must not move stock to Damage twice",
        )

    def _qty_at_damage(self):
        damage_loc = self.env["stock.location"].search([("wms_is_damage", "=", True)], limit=1)
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", damage_loc.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def test_breakdown_tracks_damage_and_repair(self):
        """5 on shelf -> damage 1 -> shelf 4 / damaged 1; start repair ->
        damaged 0 / under-repair 1; finish -> back on shelf 5."""
        self.assertEqual(self.tool.wms_qty_on_shelf, 5)
        self.assertEqual(self.tool.wms_qty_damaged, 0)
        dmg = self._damage()
        dmg.action_confirm()
        self.tool.invalidate_recordset()
        self.assertEqual(self.tool.wms_qty_on_shelf, 4)
        self.assertEqual(self.tool.wms_qty_damaged, 1)
        dmg.action_create_repair_order()
        repair = dmg.repair_order_id
        repair.action_start_repair()
        self.tool.invalidate_recordset()
        self.assertEqual(self.tool.wms_qty_damaged, 0)
        self.assertEqual(self.tool.wms_qty_under_repair, 1)
        repair.action_finish_repair()
        self.tool.invalidate_recordset()
        self.assertEqual(self.tool.wms_qty_under_repair, 0)
        self.assertEqual(self.tool.wms_qty_on_shelf, 5, "repaired unit back on shelf")

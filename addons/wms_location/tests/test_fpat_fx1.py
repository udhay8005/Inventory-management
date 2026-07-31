"""FPAT FX-1: the FIFO planner must NEVER pull from Damage or Repair-Out
locations. The previous code only excluded by usage; both flagged locations are
usage='internal'. The auditor's Critical#1 scenario: stock that has been moved
to the Damage location must not be re-issued back to cows.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx1")
class TestFpatFx1FifoExcludesDamage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.product = cls.env["product.product"].create(
            {
                "name": "FX1 FIFO Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )

    def _damage_location(self):
        # Created by the wms_repair_damage hooks; should always exist.
        return self.env["stock.location"].search([("wms_is_damage", "=", True)], limit=1)

    def test_planner_skips_damage_location_when_only_source(self):
        damage_loc = self._damage_location()
        self.assertTrue(damage_loc, "wms_is_damage location should exist")
        # Place stock ONLY in the Damage location.
        self.env["stock.quant"]._update_available_quantity(self.product, damage_loc, 10.0)
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.product.id, 5.0, parent_location_id=self.wh.lot_stock_id.id
        )
        self.assertEqual(plan, [], "planner must return empty plan when only source is Damage")
        self.assertAlmostEqual(missing, 5.0, places=3, msg="full quantity reported as missing")

    def test_planner_skips_repair_location_when_only_source(self):
        repair_loc = self.env["stock.location"].search([("wms_is_repair", "=", True)], limit=1)
        self.assertTrue(repair_loc, "wms_is_repair location should exist")
        self.env["stock.quant"]._update_available_quantity(self.product, repair_loc, 7.0)
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.product.id, 3.0, parent_location_id=self.wh.lot_stock_id.id
        )
        self.assertEqual(plan, [], "planner must return empty plan when only source is Repair-Out")
        self.assertAlmostEqual(missing, 3.0, places=3)

    def test_planner_uses_storage_when_both_present(self):
        damage_loc = self._damage_location()
        floor = self.env["stock.location"].create(
            {
                "name": "FX1 Floor",
                "usage": "internal",
                "location_id": self.wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        # 8 on damage (must be ignored) + 4 on a storage floor (must be planned).
        self.env["stock.quant"]._update_available_quantity(self.product, damage_loc, 8.0)
        self.env["stock.quant"]._update_available_quantity(self.product, floor, 4.0)
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.product.id, 3.0, parent_location_id=self.wh.lot_stock_id.id
        )
        self.assertTrue(plan, "planner must find the storage quant")
        for quant, _take in plan:
            self.assertFalse(quant.location_id.wms_is_damage, "no plan line may come from Damage")
            self.assertFalse(
                quant.location_id.wms_is_repair, "no plan line may come from Repair-Out"
            )
        self.assertAlmostEqual(missing, 0.0, places=3)

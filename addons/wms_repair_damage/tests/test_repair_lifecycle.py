"""Medium - the repair lifecycle (draft -> in_repair -> done / scrapped) and its
audit-triplet guard had no automated coverage beyond the positive-qty SQL
constraint. This drives the full happy path, the scrap path, and asserts the
guard blocks an order missing its audit triplet."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_repair")
class TestRepairLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env.ref("stock.warehouse0")
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "Repair Keeper"})
        cls.product = cls.env["product.product"].create(
            {"name": "Repairable Tool", "is_storable": True}
        )
        Loc = cls.env["stock.location"]
        cls.damage_loc = Loc.search(
            [("wms_is_damage", "=", True), ("id", "child_of", cls.wh.view_location_id.id)],
            limit=1,
        )
        cls.repair_loc = Loc.search(
            [("wms_is_repair", "=", True), ("id", "child_of", cls.wh.view_location_id.id)],
            limit=1,
        )
        cls.dest = cls.wh.lot_stock_id

    def _on_hand(self, loc):
        return self.env["stock.quant"]._get_available_quantity(self.product, loc)

    def _order(self, **extra):
        vals = {"product_id": self.product.id, "quantity": 5.0, "original_slot_id": self.dest.id}
        vals.update(extra)
        return self.env["wms.repair.order"].create(vals)

    def _full_order(self):
        return self._order(
            wms_reported_by="Tester",
            wms_authorized_by="Supervisor",
            wms_storekeeper_id=self.keeper.id,
        )

    def test_start_requires_audit_triplet(self):
        order = self._order()  # no triplet
        with self.assertRaises(UserError):
            order.action_start_repair()
        self.assertEqual(order.state, "draft")

    def test_full_lifecycle_moves_stock(self):
        self.assertTrue(
            self.damage_loc and self.repair_loc,
            "post_init must create the Damage/Repair locations",
        )
        self.env["stock.quant"]._update_available_quantity(self.product, self.damage_loc, 5.0)
        order = self._full_order()

        order.action_start_repair()
        self.assertEqual(order.state, "in_repair")
        self.assertAlmostEqual(self._on_hand(self.repair_loc), 5.0, places=3)

        order.action_finish_repair()
        self.assertEqual(order.state, "done")
        self.assertAlmostEqual(self._on_hand(self.dest), 5.0, places=3)
        self.assertAlmostEqual(self._on_hand(self.repair_loc), 0.0, places=3)

    def test_scrap_from_repair_writes_off(self):
        self.env["stock.quant"]._update_available_quantity(self.product, self.damage_loc, 5.0)
        order = self._full_order()
        order.action_start_repair()
        order.action_scrap()
        self.assertEqual(order.state, "scrapped")
        self.assertAlmostEqual(self._on_hand(self.repair_loc), 0.0, places=3)

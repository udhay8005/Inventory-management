"""Fuel log — generator/vehicle refuelling that decrements the diesel stock.

Covers the operational contract:
  * confirm moves the filled quantity out of the tank slot (stock drops) and
    snapshots the value,
  * the meter reading is required once a meter type is chosen,
  * the audit field (filled_by) is required to confirm,
  * you can't log more than the tank actually holds,
  * quantity must be positive (DB CHECK),
  * a confirmed log is frozen against a non-manager keeper.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_fuel")
class TestFuelLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        # Fuel is drawn from a floor/slot location — mirror a diesel tank bay.
        cls.tank = cls.env["stock.location"].create(
            {
                "name": "FUEL Tank Bay",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "FUEL Keeper"})
        cls.diesel = cls.env["product.product"].create(
            {
                "name": "FUEL Diesel",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
                "standard_price": 90.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.diesel, cls.tank, 100.0)

    def _log(self, **extra):
        vals = {
            "product_id": self.diesel.id,
            "quantity": 20.0,
            "source_slot_id": self.tank.id,
            "asset": "generator",
            "asset_name": "Generator 1",
            "filled_by": "Ramesh",
            "wms_storekeeper_id": self.keeper.id,
        }
        vals.update(extra)
        return self.env["wms.fuel.log"].create(vals)

    def _on_hand(self):
        return self.env["stock.quant"]._get_available_quantity(self.diesel, self.tank)

    def test_confirm_decrements_stock_and_snapshots_value(self):
        start = self._on_hand()
        log = self._log(quantity=20.0)
        self.assertTrue(log.name.startswith("FUEL-"), "name comes from the sequence")
        log.action_confirm()
        self.assertEqual(log.state, "confirmed")
        self.assertTrue(log.picking_id, "confirm creates a stock picking")
        self.assertEqual(log.picking_id.state, "done")
        self.assertAlmostEqual(
            self._on_hand(),
            start - 20.0,
            places=2,
            msg="diesel stock must drop by the filled quantity",
        )
        self.assertAlmostEqual(log.fuel_value, 20.0 * 90.0, places=2)

    def test_meter_reading_required_when_meter_set(self):
        log = self._log(meter_type="hours", meter_reading=0.0)
        with self.assertRaises(UserError):
            log.action_confirm()

    def test_missing_filled_by_blocks_confirm(self):
        log = self._log(filled_by="")
        with self.assertRaises(UserError):
            log.action_confirm()

    def test_over_tank_quantity_blocked(self):
        with self.assertRaises(UserError):
            self._log(quantity=1000.0)  # tank only holds 100

    def test_negative_quantity_blocked(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self._log(quantity=-5.0)

    def test_confirmed_log_is_keeper_locked(self):
        log = self._log()
        log.action_confirm()
        keeper_user = self.env["res.users"].create(
            {
                "name": "Fuel Keeper User",
                "login": "fuel_keeper_user",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("wms_location.group_wms_can_scan_issue").id,
                        ],
                    )
                ],
            }
        )
        with self.assertRaises(AccessError):
            log.with_user(keeper_user).write({"quantity": 5.0})

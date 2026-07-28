# -*- coding: utf-8 -*-
"""UAT R3 — settle the "fuel needs an expiry" finding with proof.

Fluids are auto lot+expiry tracked (wms_perishable). The engine UAT once saw
a fuel draw fail until the lot got an expiry, suggesting no-expiry lots were
unreservable. Core Odoo's gather domain actually ADMITS lots with no
removal_date, so the failure was a fixture artifact — this test pins the
real contract:

  * a fuel draw from a batch with NO expiry date works (fuel never has one);
  * a fuel draw from an EXPIRED batch fails with the specific
    "past the expiry date" message, not the misleading "tank level changed".
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_uat_r3")
class TestFuelNoExpiry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.tank = cls.env["stock.location"].create(
            {
                "name": "R3-FUEL-TANK",
                "usage": "internal",
                "location_id": cls.warehouse.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        cls.keeper = cls.env["wms.storekeeper"].create({"name": "R3 Fuel Keeper"})
        cls.diesel = cls.env["product.template"].create(
            {"name": "R3 Diesel", "wms_product_kind": "fluid"}
        )
        cls.product = cls.diesel.product_variant_id

    def _stock_lot(self, name, qty, expiry=None):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.product.id,
                "company_id": self.warehouse.company_id.id,
            }
        )
        if expiry is not None:
            lot.expiration_date = expiry
        self.env["stock.quant"]._update_available_quantity(self.product, self.tank, qty, lot_id=lot)
        return lot

    def _fuel(self, qty):
        log = self.env["wms.fuel.log"].create(
            {
                "product_id": self.product.id,
                "quantity": qty,
                "source_slot_id": self.tank.id,
                "asset": "generator",
                "asset_name": "Gen 1",
                "meter_type": "hours",
                "meter_reading": 100,
                "filled_by": "Tester",
                "wms_storekeeper_id": self.keeper.id,
            }
        )
        log.action_confirm()
        return log

    def test_fuel_draw_from_no_expiry_lot_works(self):
        """The fluid kind auto-tracks lots+expiry, but a fuel batch carries
        no expiry date — the draw must still reserve and confirm."""
        self.assertTrue(
            self.product.use_expiration_date,
            "fluid kind must be expiry-tracked (perishable auto-tracking)",
        )
        self._stock_lot("R3-FUEL-NOEXP", 20)
        log = self._fuel(8)
        self.assertEqual(log.state, "confirmed")
        quants = self.env["stock.quant"].search(
            [("product_id", "=", self.product.id), ("location_id", "=", self.tank.id)]
        )
        self.assertEqual(sum(quants.mapped("quantity")), 12, "tank drops 20 -> 12 (-8 L)")

    def test_fuel_draw_from_expired_lot_names_the_cause(self):
        """An expired batch is unreservable; the error must say WHY (expiry)
        instead of the misleading concurrency message."""
        self._stock_lot("R3-FUEL-EXP", 20, expiry=fields.Datetime.now() - timedelta(days=5))
        with self.assertRaises(UserError) as caught:
            self._fuel(5)
        self.assertIn(
            "expiry",
            str(caught.exception).lower(),
            "the error must name the expiry cause, got: %s" % caught.exception,
        )

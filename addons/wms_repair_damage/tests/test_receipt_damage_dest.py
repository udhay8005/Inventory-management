"""D4 — a Scan Receipt must refuse a Damage / Repair location as its
destination.

The FIFO issue picker deliberately EXCLUDES wms_is_damage / wms_is_repair
locations (broken / in-repair stock must never be issued back to cows). So if a
keeper scans a barcoded Damage location on a receipt, the good incoming stock
lands somewhere the picker can never reach — on-hand but un-issuable, silently
stranded. The guard lives in wms_barcode.scan_receipt.action_validate; this test
lives in wms_repair_damage because the wms_is_damage / wms_is_repair flags (and
the auto-created Damage / Repair-Out locations) are defined here.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_receipt_damage_dest")
class TestReceiptDamageDest(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        Loc = cls.env["stock.location"]
        # post_init_locations auto-creates these under every warehouse.
        cls.damage_loc = Loc.search(
            [("wms_is_damage", "=", True), ("id", "child_of", cls.wh.view_location_id.id)],
            limit=1,
        )
        cls.repair_loc = Loc.search(
            [("wms_is_repair", "=", True), ("id", "child_of", cls.wh.view_location_id.id)],
            limit=1,
        )
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "RDD Keeper"})
        cls.product = cls.env["product.product"].create(
            {"name": "RDD Product", "type": "consu", "is_storable": True, "barcode": "RDD001"}
        )
        # a legitimate floor zone for the positive control
        cls.floor = Loc.create(
            {
                "name": "RDD Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    def _receipt(self, dest):
        """Build a receipt whose single line targets ``dest`` directly — this is
        exactly what the location-scan branch writes (it bypasses the field's
        UI domain, which is the real-world hole)."""
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "qc_passed": True, "storekeeper_id": self.keeper.id}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.product.id,
                "quantity": 3.0,
                "location_dest_id": dest.id,
            }
        )
        return wiz

    def test_post_init_created_damage_repair_locations(self):
        self.assertTrue(
            self.damage_loc and self.repair_loc,
            "post_init must create the Damage / Repair-Out locations",
        )

    def test_receipt_into_damage_location_refused(self):
        wiz = self._receipt(self.damage_loc)
        with self.assertRaises(UserError) as cm:
            wiz.action_validate()
        self.assertIn("Damage or Repair location", cm.exception.args[0])
        self.assertFalse(wiz.picking_id, "no picking created — stock not stranded")

    def test_receipt_into_repair_location_refused(self):
        wiz = self._receipt(self.repair_loc)
        with self.assertRaises(UserError):
            wiz.action_validate()
        self.assertFalse(wiz.picking_id)

    def test_receipt_into_floor_still_validates(self):
        """The guard must not block a legitimate slot / floor destination."""
        wiz = self._receipt(self.floor)
        wiz.action_validate()
        self.assertTrue(wiz.picking_id and wiz.picking_id.state == "done")

"""V20-018 — near-expiry receiving guard: a receipt whose batch has less than
the minimum shelf life is blocked, and only a Manager can accept it."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestShortDatedReceipt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "SD Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "SD Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "SD Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "SDMED01",
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "SD Manager",
                "login": "sd_manager",
                "group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)],
            }
        )
        cls.clerk = cls.env["res.users"].create(
            {
                "name": "SD Clerk",
                "login": "sd_clerk",
                "group_ids": [(4, cls.env.ref("wms_location.group_wms_can_scan_receive").id)],
            }
        )

    def _wizard(self, days_to_expiry, batch="SD-B", qty=10):
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.med.id,
                "quantity": qty,
                "location_dest_id": self.floor.id,
                "wms_batch": batch,
                "wms_expiry": fields.Date.today() + timedelta(days=days_to_expiry),
            }
        )
        return wiz

    def test_short_dated_receipt_blocked(self):
        wiz = self._wizard(days_to_expiry=10)  # < 60-day default
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_far_dated_receipt_ok(self):
        wiz = self._wizard(days_to_expiry=365, batch="SD-FAR")
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "far-dated stock receives normally")

    def test_manager_can_accept_short_dated(self):
        wiz = self._wizard(days_to_expiry=10, batch="SD-OVR")
        wiz.with_user(self.manager).action_receive_short_dated_override()
        self.assertTrue(wiz.picking_id, "manager override receives the short-dated batch")

    def test_non_manager_cannot_override(self):
        wiz = self._wizard(days_to_expiry=10, batch="SD-NO")
        with self.assertRaises(UserError):
            wiz.with_user(self.clerk).action_receive_short_dated_override()

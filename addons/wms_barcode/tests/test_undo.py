"""Batch 4 — Undo window. A storekeeper can reverse a recent Scan Issue with one
click; the compensating internal transfer puts the stock back WITHOUT deleting
anything. These tests prove the happy path restores stock, a second undo is
refused, and the time window gates availability.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_undo")
class TestUndo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "UAT Keeper U"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "UNDO-TEST Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "UNDOTEST001",
                "wms_product_kind": "consumable",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 10.0)
        # Make sure the undo window is open for the tests.
        cls.env["ir.config_parameter"].sudo().set_param("wms_reports.undo_minutes", "15")

    def _on_hand(self):
        return self.env["stock.quant"]._get_available_quantity(self.product, self.stock)

    def _issue(self, qty=3.0):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": "UNDOTEST001",
                "taken_by": "Test Taker",
                "ordered_by": "Test Orderer",
                "usage_note": "undo test",
                "storekeeper_id": self.keeper.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        return wiz.picking_id

    def test_undo_restores_stock(self):
        start = self._on_hand()
        picking = self._issue(3.0)
        self.assertAlmostEqual(self._on_hand(), start - 3.0, places=3)
        self.assertTrue(picking.wms_undo_available, "a fresh scan issue should be undoable")

        picking.action_wms_undo()

        self.assertTrue(picking.wms_reversed_by_id, "original must point at the reversal")
        self.assertTrue(picking.wms_reversed_by_id.wms_is_undo, "reversal carries the undo flag")
        self.assertFalse(picking.wms_undo_available, "an undone transfer is no longer undoable")
        self.assertAlmostEqual(self._on_hand(), start, places=3, msg="stock fully restored")

    def test_second_undo_is_refused(self):
        picking = self._issue(2.0)
        picking.action_wms_undo()
        with self.assertRaises(UserError):
            picking.action_wms_undo()

    def test_window_zero_disables_undo(self):
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.undo_minutes", "0")
        picking = self._issue(2.0)
        self.assertFalse(picking.wms_undo_available, "window 0 means undo is off")
        with self.assertRaises(UserError):
            picking.action_wms_undo()
        # restore for any later test ordering
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.undo_minutes", "15")

    def test_reversal_is_not_itself_undoable(self):
        picking = self._issue(2.0)
        action = picking.action_wms_undo()
        reversal = self.env["stock.picking"].browse(action["res_id"])
        self.assertFalse(
            reversal.wms_undo_available, "the compensating transfer must not be undoable"
        )

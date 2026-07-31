# -*- coding: utf-8 -*-
"""Return-integrity tests (UAT R3): a Scan Return must REVERSE an issue,
never fabricate stock.

Found in live operator UAT: a return for 23 units of a drill that only ever
had 2 issued was accepted, sourced from *Vendors* — inventing 23 phantom
units. These tests pin the fixed contract:

  * a return is capped at (issued minus already-returned) per product;
  * a return with nothing outstanding is refused outright;
  * the return's stock moves come FROM the use-location the issue delivered
    to (a reversal), not from Vendors;
  * a good return prefills / defaults to the slot the issue drew from;
  * a Damaged / Needs-repair return is quarantined into the Damage location,
    never onto an issuable shelf slot.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_return_guard")
class TestScanReturnGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.trust_use = cls.env.ref("wms_location.stock_location_trust_use")
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "RET-GUARD-SLOT",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.keeper = cls.env["wms.storekeeper"].create({"name": "Return Guard Keeper"})
        cls.dept = cls.env["wms.department"].search([], limit=1) or cls.env[
            "wms.department"
        ].create({"name": "Return Guard Dept"})
        cls.tool = cls.env["product.template"].create(
            {
                "name": "RET-GUARD Drill",
                "wms_product_kind": "tool",
                "is_storable": True,
                "barcode": "RET-GUARD-DRILL",
            }
        )
        cls.product = cls.tool.product_variant_id
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.slot, 4)

    def _onhand(self, location):
        quants = self.env["stock.quant"].search(
            [("product_id", "=", self.product.id), ("location_id", "=", location.id)]
        )
        return sum(quants.mapped("quantity"))

    def _issue(self, qty):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.warehouse.id,
                "requested_qty": qty,
                "taken_by": "Tester",
                "storekeeper_id": self.keeper.id,
                "department_id": self.dept.id,
                "usage_note": "return-guard test",
            }
        )
        wiz.last_scan = self.tool.barcode
        wiz.action_plan()
        wiz.action_validate()
        return wiz

    def _return_wizard(self, qty, condition="good", dest=None):
        wiz = self.env["wms.scan.receipt"].create(
            {
                "warehouse_id": self.warehouse.id,
                "storekeeper_id": self.keeper.id,
                "is_return": True,
                "return_condition": condition,
                "qc_passed": True,
            }
        )
        wiz.last_scan = self.tool.barcode
        wiz.action_process_scan()
        wiz.line_ids[0].quantity = qty
        if dest is not None:
            wiz.line_ids[0].location_dest_id = dest
        return wiz

    def test_01_return_cannot_exceed_outstanding(self):
        """Issued 1 -> returning 3 must be refused (the 23-drill bug)."""
        self._issue(1)
        wiz = self._return_wizard(3)
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_02_return_with_nothing_outstanding_refused(self):
        """Nothing issued -> any return is refused outright."""
        wiz = self._return_wizard(1)
        with self.assertRaises(UserError):
            wiz.action_validate()

    def test_03_return_reverses_from_use_location(self):
        """The return's stock comes FROM the use-location (a reversal), the
        slot count is restored, and Vendors is never touched."""
        vendors = self.env.ref("stock.stock_location_suppliers")
        vendors_before = self._onhand(vendors)
        self._issue(1)
        self.assertEqual(self._onhand(self.trust_use), 1)
        self.assertEqual(self._onhand(self.slot), 3)
        wiz = self._return_wizard(1)
        wiz.action_validate()
        self.assertTrue(wiz.picking_id.wms_is_scan_return)
        move = wiz.picking_id.move_ids
        self.assertEqual(
            move.location_id,
            self.trust_use,
            "a return must reverse the issue from the use-location, not Vendors",
        )
        self.assertEqual(self._onhand(self.trust_use), 0, "use-location emptied")
        self.assertEqual(self._onhand(self.slot), 4, "slot restored to its full count")
        self.assertEqual(
            self._onhand(vendors),
            vendors_before,
            "Vendors stock must be untouched by a return",
        )

    def test_04_scan_prefills_original_slot(self):
        """Scanning in return mode prefills the slot the issue drew from."""
        self._issue(1)
        wiz = self._return_wizard(1)
        self.assertEqual(
            wiz.line_ids[0].location_dest_id,
            self.slot,
            "return line must prefill the original issue slot",
        )
        wiz.action_validate()
        self.assertEqual(self._onhand(self.slot), 4)

    def test_05_damaged_return_quarantined(self):
        """A Damaged return lands in the Damage location — never on a shelf
        slot — so broken stock can't be scan-issued."""
        damage = self.env["stock.location"].search([("wms_is_damage", "=", True)], limit=1)
        if not damage:
            self.skipTest("wms_repair_damage not installed — no Damage location")
        self._issue(1)
        wiz = self._return_wizard(1, condition="damaged", dest=self.slot)
        wiz.action_validate()
        self.assertEqual(
            wiz.line_ids[0].location_dest_id,
            damage,
            "damaged return must be forced into the Damage location",
        )
        self.assertEqual(self._onhand(damage), 1, "unit quarantined in Damage")
        self.assertEqual(self._onhand(self.slot), 3, "shelf slot must NOT get it back")

    def test_06_second_return_blocked_after_full_return(self):
        """Once everything issued has come back, another return is refused —
        the ledger counts past returns."""
        self._issue(1)
        self._return_wizard(1).action_validate()
        wiz = self._return_wizard(1)
        with self.assertRaises(UserError):
            wiz.action_validate()

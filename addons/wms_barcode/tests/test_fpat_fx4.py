"""FPAT FX-4 regressions: concurrency hardening.

  * Scan Issue + Scan Receipt: idempotency picking_id check moved INSIDE the
    wizard row lock. A second call to action_validate that sees the wizard
    row locked with picking_id already set must short-circuit.
  * Onboard wizard: a re-fire of _do_onboard on a completed wizard raises
    rather than silently creating duplicate products with different auto-SKUs.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx4")
class TestFpatFx4Idempotency(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "FX4 Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "FX4 Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
                "barcode": "FX4PROBE1",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.wh.lot_stock_id, 20.0)

    def test_scan_issue_double_validate_is_idempotent_after_lock(self):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": 3.0,
                "last_scan": "FX4PROBE1",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "FX4",
                "storekeeper_id": self.keeper.id,
                "issued_for": "other",
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        first = wiz.picking_id
        self.assertTrue(first)
        # Second call from the same env exercises both the row-lock check
        # AND the in-Python fast-path. Must return the same picking, no
        # second deduction.
        on_hand_before = self.env["stock.quant"]._get_available_quantity(
            self.product, self.wh.lot_stock_id
        )
        wiz.action_validate()
        self.assertEqual(wiz.picking_id, first)
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.product, self.wh.lot_stock_id),
            on_hand_before,
            places=3,
        )

    def test_scan_receipt_double_validate_is_idempotent_after_lock(self):
        wiz = self.env["wms.scan.receipt"].create(
            {
                "warehouse_id": self.wh.id,
                "qc_passed": True,
                "storekeeper_id": self.keeper.id,
            }
        )
        self.env["wms.scan.receipt.line"].create(
            {"wizard_id": wiz.id, "product_id": self.product.id, "quantity": 5.0}
        )
        wiz.action_validate()
        first = wiz.picking_id
        self.assertTrue(first)
        # Capture state, then re-validate.
        qty_before = self.env["stock.quant"]._get_available_quantity(
            self.product, self.wh.lot_stock_id
        )
        wiz.action_validate()
        self.assertEqual(wiz.picking_id, first)
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(self.product, self.wh.lot_stock_id),
            qty_before,
            places=3,
        )


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx4")
class TestFpatFx4OnboardDoubleClick(TransactionCase):
    def test_re_firing_onboard_after_success_raises(self):
        wiz = self.env["wms.product.onboard"].create(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "FX4 Onboard Probe",
                            "wms_product_kind": "consumable",
                            "initial_qty": 0,
                        },
                    )
                ]
            }
        )
        wiz._validate()
        wiz._do_onboard()
        # The summary field is set at the end of the first call. A second
        # call must raise rather than silently creating a duplicate product
        # with a different auto-SKU.
        with self.assertRaises(UserError):
            wiz._do_onboard()
        # And no duplicate was created.
        self.assertEqual(
            self.env["product.product"].search_count([("name", "=", "FX4 Onboard Probe")]),
            1,
        )

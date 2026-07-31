# -*- coding: utf-8 -*-
"""One-click expired-stock sweep.

The warehouse photos showed Povidone (exp 4/2025) and Zenbloat (exp 10/2024)
still on the shelf in mid-2026 — expired stock sitting beside good stock in a
medicine room. Hunting it batch by batch is the chore nobody does, so the
sweep finds every expired batch that still holds stock, freezes it in
quarantine (which excludes it from issuing) and hands the Manager one record
to decide on.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_expired_sweep")
class TestExpiredSweep(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The sweep is Manager-gated (it freezes stock). The Odoo test user is
        # NOT a WMS manager by default, so grant the group — the gate itself is
        # covered by test_05 below.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "SWEEP-TEST-SLOT",
                "usage": "internal",
                "location_id": cls.warehouse.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.template"].create(
            {"name": "SWEEP Povidone", "wms_product_kind": "medicine"}
        )
        cls.product = cls.med.product_variant_id

    def _lot(self, name, days, qty=10):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.product.id,
                "company_id": self.warehouse.company_id.id,
            }
        )
        lot.expiration_date = fields.Datetime.now() + timedelta(days=days)
        self.env["stock.quant"]._update_available_quantity(self.product, self.slot, qty, lot_id=lot)
        return lot

    def test_01_sweep_quarantines_only_expired_batches(self):
        expired = self._lot("SWEEP-EXPIRED", -30)
        good = self._lot("SWEEP-GOOD", 120)
        self.assertEqual(expired.wms_lot_state, "available")

        action = self.env["wms.lot.quarantine"].action_sweep_expired()

        self.assertEqual(expired.wms_lot_state, "quarantine", "the expired batch must be frozen")
        self.assertEqual(good.wms_lot_state, "available", "an in-date batch must be left alone")
        self.assertEqual(action.get("res_model"), "wms.lot.quarantine")
        record = self.env["wms.lot.quarantine"].browse(action["res_id"])
        self.assertIn(expired, record.lot_ids)
        self.assertNotIn(good, record.lot_ids)
        self.assertIn("expired-stock sweep", record.reason)

    def test_02_sweep_is_quiet_when_shelves_are_clean(self):
        self._lot("SWEEP-FRESH", 200)
        action = self.env["wms.lot.quarantine"].action_sweep_expired()
        self.assertEqual(
            action.get("tag"),
            "display_notification",
            "nothing expired -> a friendly notification, not an empty record",
        )

    def test_03_sweep_ignores_batches_with_no_stock(self):
        """An expired batch that is already used up must not be swept — there
        is nothing on the shelf to quarantine."""
        empty = self.env["stock.lot"].create(
            {
                "name": "SWEEP-EMPTY",
                "product_id": self.product.id,
                "company_id": self.warehouse.company_id.id,
            }
        )
        empty.expiration_date = fields.Datetime.now() - timedelta(days=10)
        action = self.env["wms.lot.quarantine"].action_sweep_expired()
        self.assertEqual(action.get("tag"), "display_notification")
        self.assertEqual(empty.wms_lot_state, "available")

    def test_04_sweep_does_not_re_hold_an_already_quarantined_batch(self):
        expired = self._lot("SWEEP-TWICE", -5)
        self.env["wms.lot.quarantine"].action_sweep_expired()
        self.assertEqual(expired.wms_lot_state, "quarantine")
        # Second run: nothing left to sweep.
        action = self.env["wms.lot.quarantine"].action_sweep_expired()
        self.assertEqual(action.get("tag"), "display_notification")

    def test_05_sweep_is_manager_only(self):
        """A Store Keeper cannot freeze stock — the sweep stays Manager-gated."""
        keeper = self.env["res.users"].create(
            {
                "name": "Sweep Keeper",
                "login": "sweep_keeper_test",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_user").id])],
            }
        )
        self._lot("SWEEP-ACL", -3)
        with self.assertRaises(UserError):
            self.env["wms.lot.quarantine"].with_user(keeper).action_sweep_expired()

"""V20-020 — the migration wizard brings legacy (non lot-tracked) perishable
products onto lot tracking: zero-stock products clean-flip; stock-bearing
products get their on-hand assigned to a LEGACY lot first, then flip. Dry run
changes nothing."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestMigration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "MG Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.env.user.write({"group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)]})

    def _legacy_perishable(self, name, on_hand=0):
        # A medicine is auto lot-tracked on create (V20-003); force it back to
        # non-lot (no stock yet, so the flip is allowed) to simulate a legacy
        # v19 perishable product, then optionally seed plain (no-lot) stock.
        prod = self.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
            }
        )
        prod.product_tmpl_id.write({"tracking": "none", "use_expiration_date": False})
        if on_hand:
            self.env["stock.quant"]._update_available_quantity(prod, self.floor, on_hand)
        return prod

    def _wizard(self):
        return self.env["wms.lot.migration"].create({})

    def test_dry_run_changes_nothing(self):
        prod = self._legacy_perishable("MG-DRY", on_hand=3)
        wiz = self._wizard()
        wiz.action_dry_run()
        self.assertEqual(prod.tracking, "none", "dry run must not change tracking")
        self.assertIn("DRY RUN", wiz.report)
        self.assertIn(prod.display_name, wiz.report)

    def test_zero_stock_clean_flip(self):
        prod = self._legacy_perishable("MG-ZERO", on_hand=0)
        self._wizard().action_migrate()
        self.assertEqual(prod.tracking, "lot", "zero-stock perishable is flipped to lot")
        self.assertTrue(prod.product_tmpl_id.use_expiration_date)

    def test_stock_bearing_gets_legacy_lot(self):
        prod = self._legacy_perishable("MG-STOCK", on_hand=7)
        self._wizard().action_migrate()
        self.assertEqual(prod.tracking, "lot")
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", prod.id),
                ("location_id", "=", self.floor.id),
                ("quantity", ">", 0),
            ]
        )
        self.assertTrue(quants, "on-hand survived the migration")
        self.assertTrue(all(q.lot_id for q in quants), "on-hand was assigned to a lot (no orphans)")
        self.assertTrue(
            all("LEGACY-" in (q.lot_id.name or "") for q in quants), "assigned to a LEGACY lot"
        )

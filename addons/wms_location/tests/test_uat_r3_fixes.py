# -*- coding: utf-8 -*-
"""UAT R3 fixes in wms_location:

  * SKU regenerate falls back to the per-kind KIND-NNNNN sequence when the
    product has a Kind but no Family/Brand (previously it refused, leaving
    a kind-set-after-save product with no SKU and no barcode at all);
  * a WMS-kind good defaults to Track Inventory ON at create;
  * a WMS slot / floor zone can never be driven negative by a transfer
    (the -2-drills phantom seen live), while staging locations keep Odoo's
    native behaviour and the wms_allow_negative escape hatch works.
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_uat_r3")
class TestUatR3LocationFixes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "R3-FIX-SLOT",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    # ---- SKU regenerate fallback ----------------------------------------
    def test_regen_sku_kind_only_falls_back_to_sequence(self):
        """Kind set after the first save -> Regenerate now yields the plain
        sequence SKU instead of demanding Family+Brand."""
        tmpl = self.env["product.template"].create({"name": "R3 Late-Kind Bolt"})
        self.assertFalse(tmpl.default_code, "no kind at create -> no auto SKU")
        tmpl.wms_product_kind = "spare"
        tmpl.action_wms_regenerate_sku()
        self.assertTrue(
            tmpl.default_code and tmpl.default_code.startswith("SPARE"),
            "fallback must allocate a SPARE-NNNNN sequence SKU, got %r" % tmpl.default_code,
        )
        self.assertEqual(
            tmpl.product_variant_id.barcode,
            tmpl.default_code,
            "barcode must re-sync to the fallback SKU",
        )

    def test_regen_sku_without_kind_still_blocks(self):
        tmpl = self.env["product.template"].create({"name": "R3 Kindless"})
        with self.assertRaises(UserError):
            tmpl.action_wms_regenerate_sku()

    # ---- Track Inventory default ----------------------------------------
    def test_wms_kind_defaults_storable(self):
        tmpl = self.env["product.template"].create(
            {"name": "R3 Auto-Storable", "wms_product_kind": "spare"}
        )
        self.assertTrue(tmpl.is_storable, "a WMS-kind good must track inventory")

    def test_explicit_storable_false_wins(self):
        tmpl = self.env["product.template"].create(
            {
                "name": "R3 Explicit Non-Storable",
                "wms_product_kind": "spare",
                "is_storable": False,
            }
        )
        self.assertFalse(tmpl.is_storable, "an explicit caller value must win")

    def test_no_kind_keeps_odoo_default(self):
        tmpl = self.env["product.template"].create({"name": "R3 Plain Product"})
        self.assertFalse(tmpl.is_storable, "no WMS kind -> native Odoo default untouched")

    # ---- Negative-slot guard --------------------------------------------
    def _make_stocked_product(self, qty):
        tmpl = self.env["product.template"].create(
            {"name": "R3 Guarded", "wms_product_kind": "spare"}
        )
        self.env["stock.quant"]._update_available_quantity(tmpl.product_variant_id, self.slot, qty)
        return tmpl.product_variant_id

    def test_transfer_cannot_drive_slot_negative(self):
        """Validating an internal transfer for MORE than the slot holds must
        be refused — the live walkthrough left a slot at -2 this way."""
        product = self._make_stocked_product(4)
        dest = self.env["stock.location"].create(
            {
                "name": "R3-FIX-SLOT-B",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "floor",
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 10,
                "company_id": self.warehouse.company_id.id,
                "procure_method": "make_to_stock",
                "location_id": self.slot.id,
                "location_dest_id": dest.id,
            }
        )
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = 10  # force over-pick, the live scenario
        move.picked = True
        with self.assertRaises(ValidationError):
            move._action_done()

    def test_full_transfer_still_works(self):
        product = self._make_stocked_product(4)
        dest = self.env["stock.location"].create(
            {
                "name": "R3-FIX-SLOT-C",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "floor",
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 4,
                "company_id": self.warehouse.company_id.id,
                "procure_method": "make_to_stock",
                "location_id": self.slot.id,
                "location_dest_id": dest.id,
            }
        )
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = 4
        move.picked = True
        move._action_done()
        quants = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", dest.id)]
        )
        self.assertEqual(sum(quants.mapped("quantity")), 4)

    def test_escape_hatch_context(self):
        product = self._make_stocked_product(1)
        self.env["stock.quant"].with_context(wms_allow_negative=True)._update_available_quantity(
            product, self.slot, -3
        )
        quants = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", self.slot.id)]
        )
        self.assertEqual(
            sum(quants.mapped("quantity")),
            -2,
            "wms_allow_negative context must bypass the guard for data repair",
        )

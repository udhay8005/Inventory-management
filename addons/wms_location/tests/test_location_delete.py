# -*- coding: utf-8 -*-
"""Tests for the @api.ondelete guard on stock.location added in
wms_location 19.0.3.0.0. Verifies an admin cannot accidentally delete a
WMS-typed location that holds stock or has audit history.

Uses wms_location_type='floor' for fixtures because:
- It is in the protected set {rack, compartment, slot, floor}, so the
  guard fires on it.
- It has no hierarchy-parent constraints (unlike slot which must live
  under a compartment, and compartment which must live under a rack).
- The principle the guard enforces is identical across all four
  protected types — proving it on floor proves it for the set.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_delete")
class TestStockLocationDeleteGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        cls.stock = cls.env.ref("stock.stock_location_stock")
        cls.parent_floor = cls.Location.create(
            {
                "name": "WMS-TEST-FLOOR-PARENT",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    def _make_floor(self, name, parent=None):
        return self.Location.create(
            {
                "name": name,
                "usage": "internal",
                "location_id": (parent or self.parent_floor).id,
                "wms_location_type": "floor",
            }
        )

    def test_delete_floor_with_children_blocks(self):
        """A protected location with sub-locations must refuse delete."""
        self._make_floor("WMS-TEST-FLOOR-CHILD")
        with self.assertRaises(UserError):
            self.parent_floor.unlink()

    def test_delete_empty_unused_floor_succeeds(self):
        """A protected location with nothing in it can be deleted."""
        floor = self._make_floor("WMS-TEST-FLOOR-EMPTY")
        floor.unlink()
        self.assertFalse(floor.exists())

    def test_delete_floor_with_live_quants_blocks(self):
        """A protected location holding > 0 stock must refuse delete."""
        floor = self._make_floor("WMS-TEST-FLOOR-Q")
        product = self.env["product.product"].create(
            {
                "name": "WMS-TEST-PRODUCT-Q",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": floor.id,
                "quantity": 5.0,
            }
        )
        with self.assertRaises(UserError):
            floor.unlink()

    def test_delete_floor_with_move_history_blocks(self):
        """A protected location with stock.move history must refuse
        delete — the audit trail's location pointer would be orphaned.

        Uses ORM create with the DEFAULT 'draft' state to avoid Odoo's
        stricter validations on 'done' moves (move_lines, picking_type,
        etc.). The @api.ondelete's history check counts ANY stock.move
        row referencing the location regardless of state, which is the
        correct policy — even cancelled/draft moves are audit history."""
        floor = self._make_floor("WMS-TEST-FLOOR-H")
        product = self.env["product.product"].create(
            {
                "name": "WMS-TEST-PRODUCT-H",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 1.0,
                "location_id": floor.id,
                "location_dest_id": self.stock.id,
                # state defaults to 'draft'
            }
        )
        with self.assertRaises(UserError):
            floor.unlink()

    def test_archive_instead_of_delete_succeeds(self):
        """Archive (active=False) must always work — it is the safe
        alternative the operator is directed to in the error message."""
        floor = self._make_floor("WMS-TEST-FLOOR-ARCH")
        floor.active = False
        self.assertFalse(floor.active)

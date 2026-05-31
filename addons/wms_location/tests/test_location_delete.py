# -*- coding: utf-8 -*-
"""Tests for the @api.ondelete guard on stock.location added in
wms_location 19.0.3.0.0. Verifies an admin cannot accidentally delete a
rack/compartment/slot that holds stock or has audit history.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_delete")
class TestStockLocationDeleteGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Location = cls.env["stock.location"]
        cls.parent = cls.Location.create({
            "name": "WMS-TEST-RACK",
            "usage": "internal",
            "wms_location_type": "rack",
        })

    def _make_slot(self, name, parent=None):
        return self.Location.create({
            "name": name,
            "usage": "internal",
            "location_id": (parent or self.parent).id,
            "wms_location_type": "slot",
        })

    def test_delete_rack_with_children_blocks(self):
        self._make_slot("WMS-TEST-SLOT-A")
        with self.assertRaises(UserError):
            self.parent.unlink()

    def test_delete_empty_unused_slot_succeeds(self):
        slot = self._make_slot("WMS-TEST-SLOT-EMPTY")
        slot.unlink()
        self.assertFalse(slot.exists())

    def test_delete_slot_with_live_quants_blocks(self):
        slot = self._make_slot("WMS-TEST-SLOT-Q")
        product = self.env["product.product"].create({
            "name": "WMS-TEST-PRODUCT-Q",
            "type": "consu",
            "is_storable": True,
        })
        self.env["stock.quant"].create({
            "product_id": product.id,
            "location_id": slot.id,
            "quantity": 5.0,
        })
        with self.assertRaises(UserError):
            slot.unlink()

    def test_delete_slot_with_move_history_blocks(self):
        slot = self._make_slot("WMS-TEST-SLOT-H")
        product = self.env["product.product"].create({
            "name": "WMS-TEST-PRODUCT-H",
            "type": "consu",
            "is_storable": True,
        })
        self.env["stock.move"].create({
            "name": "WMS-TEST-MOVE-H",
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": 1.0,
            "location_id": slot.id,
            "location_dest_id": self.env.ref("stock.stock_location_stock").id,
            "state": "done",
        })
        with self.assertRaises(UserError):
            slot.unlink()

    def test_archive_instead_of_delete_succeeds(self):
        slot = self._make_slot("WMS-TEST-SLOT-ARCH")
        slot.active = False
        self.assertFalse(slot.active)

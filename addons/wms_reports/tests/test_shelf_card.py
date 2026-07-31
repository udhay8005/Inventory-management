# -*- coding: utf-8 -*-
"""Shelf Card tests: the printable per-location card that replaces the
trust's hand-written whiteboard shelf cards.

Contract:
  * ``wms_shelf_card_data()`` lists every product in the location with the
    total quantity, per-batch quantities sorted earliest-expiry-first, the
    first dated batch flagged USE FIRST, and un-batched stock as ``loose``;
  * the QWeb report renders (one card page per location) and carries the
    product name, quantity and batch names.
"""
from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_shelf_card")
class TestShelfCard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "SHELF-CARD-SLOT",
                "usage": "internal",
                "location_id": warehouse.lot_stock_id.id,
                "wms_location_type": "floor",
                "barcode": "SHELF-CARD-SLOT",
            }
        )
        cls.med = cls.env["product.template"].create(
            {
                "name": "Shelf Card Med",
                "wms_product_kind": "medicine",
                "is_storable": True,
                "barcode": "SHELF-CARD-MED",
            }
        )
        cls.bolt = cls.env["product.template"].create(
            {
                "name": "Shelf Card Bolt",
                "wms_product_kind": "spare",
                "is_storable": True,
                "barcode": "SHELF-CARD-BOLT",
            }
        )
        Quant = cls.env["stock.quant"]
        Lot = cls.env["stock.lot"]
        company = warehouse.company_id
        # Receive the LATER expiry first so the card has to re-sort.
        cls.lot_late = Lot.create(
            {
                "name": "SC-LOT-LATE",
                "product_id": cls.med.product_variant_id.id,
                "company_id": company.id,
            }
        )
        cls.lot_early = Lot.create(
            {
                "name": "SC-LOT-EARLY",
                "product_id": cls.med.product_variant_id.id,
                "company_id": company.id,
            }
        )
        if "expiration_date" in Lot._fields:
            cls.lot_late.expiration_date = str(date.today() + timedelta(days=300))
            cls.lot_early.expiration_date = str(date.today() + timedelta(days=100))
        Quant._update_available_quantity(
            cls.med.product_variant_id, cls.slot, 40, lot_id=cls.lot_late
        )
        Quant._update_available_quantity(
            cls.med.product_variant_id, cls.slot, 60, lot_id=cls.lot_early
        )
        Quant._update_available_quantity(cls.bolt.product_variant_id, cls.slot, 7)

    def test_01_card_data_shape_and_fefo_order(self):
        cards = self.slot.wms_shelf_card_data()
        by_name = {c["product"].display_name: c for c in cards}
        med = by_name[self.med.product_variant_id.display_name]
        bolt = by_name[self.bolt.product_variant_id.display_name]
        self.assertEqual(med["qty"], 100.0)
        self.assertEqual(bolt["qty"], 7.0)
        self.assertEqual(bolt["loose"], 7.0, "un-batched stock reported as loose")
        self.assertEqual(
            [lot["name"] for lot in med["lots"]],
            ["SC-LOT-EARLY", "SC-LOT-LATE"],
            "batches must sort earliest-expiry-first",
        )
        if "expiration_date" in self.env["stock.lot"]._fields:
            self.assertTrue(
                med["lots"][0]["use_first"],
                "the earliest-expiry batch must carry the USE FIRST flag",
            )
            self.assertFalse(med["lots"][1]["use_first"])

    def test_02_report_renders(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "wms_reports.action_report_wms_shelf_card", [self.slot.id]
        )[0]
        text = html.decode()
        self.assertIn("SHELF-CARD-SLOT", text, "location header on the card")
        self.assertIn("Shelf Card Med", text, "product block rendered")
        self.assertIn("SC-LOT-EARLY", text, "batch rows rendered")

    def test_03_empty_location_renders_empty_card(self):
        empty = self.env["stock.location"].create(
            {
                "name": "SHELF-CARD-EMPTY",
                "usage": "internal",
                "location_id": self.slot.location_id.id,
                "wms_location_type": "floor",
            }
        )
        self.assertEqual(empty.wms_shelf_card_data(), [])
        html = self.env["ir.actions.report"]._render_qweb_html(
            "wms_reports.action_report_wms_shelf_card", [empty.id]
        )[0]
        self.assertIn("EMPTY", html.decode())

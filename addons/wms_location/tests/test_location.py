"""Unit tests for the rack / compartment / slot hierarchy.

Tagged with `wms` so CI can run only our tests via `--test-tags wms`.

The model is now: Rack → Compartment (can span multiple shelves) → Slot.
Shelves are grid coordinates on Compartment, not a separate location.
"""

import json

from odoo.exceptions import ValidationError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms")
class TestWmsLocation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search([], limit=1)
        self.parent = self.warehouse.lot_stock_id

    def _gen_rack(self, code="R-TEST", shelves=6, columns=3, slots=1):
        """Create a rack via the quick-grid path."""
        return (
            self.env["wms.rack.generator"]
            .create(
                {
                    "rack_code": code,
                    "parent_location_id": self.parent.id,
                    "shelf_count": shelves,
                    "column_count": columns,
                    "default_slot_count": slots,
                }
            )
            .action_generate()
        )

    # ─── happy path ─────────────────────────────────────────────────────
    def test_quick_grid_creates_full_hierarchy(self):
        self._gen_rack("R-T1", shelves=6, columns=3, slots=1)
        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-T1")], limit=1)
        compartments = self.env["stock.location"].search(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
            ]
        )
        slots = self.env["stock.location"].search(
            [
                ("location_id", "in", compartments.ids),
                ("wms_location_type", "=", "slot"),
            ]
        )
        self.assertEqual(rack.wms_shelf_count, 6)
        self.assertEqual(rack.wms_column_count, 3)
        self.assertEqual(len(compartments), 6 * 3, "6×3 = 18 compartments")
        self.assertEqual(len(slots), 6 * 3, "1 slot per compartment by default")

    def test_custom_layout_with_spanning_compartment(self):
        """Layout JSON: 6×3 grid where column 1 has one tall compartment
        covering shelves 1-3, the rest stay single-shelf."""
        compartments = []
        # Column 1: shelves 1-3 merged into one tall compartment (3 slots)
        compartments.append({"shelf_top": 1, "shelf_bottom": 3, "column_index": 1, "slot_count": 3})
        # Column 1: shelves 4-6 stay single
        for s in (4, 5, 6):
            compartments.append({"shelf_top": s, "shelf_bottom": s, "column_index": 1, "slot_count": 1})
        # Columns 2 + 3: all single-shelf
        for s in range(1, 7):
            for c in (2, 3):
                compartments.append({"shelf_top": s, "shelf_bottom": s, "column_index": c, "slot_count": 1})
        spec = {"shelves": 6, "columns": 3, "compartments": compartments}

        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-SPAN",
                "parent_location_id": self.parent.id,
                "layout_json": json.dumps(spec),
            }
        )
        gen.action_generate()

        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-SPAN")], limit=1)
        tall = self.env["stock.location"].search(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
                ("wms_column_index", "=", 1),
                ("wms_shelf_top", "=", 1),
            ],
            limit=1,
        )
        self.assertEqual(tall.wms_shelf_bottom, 3, "tall compartment spans shelves 1-3")
        self.assertEqual(tall.wms_slot_count, 3, "tall compartment has 3 slots")
        # Total compartments: 1 tall + 3 single (col 1) + 12 single (cols 2-3) = 16
        total = self.env["stock.location"].search_count(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
            ]
        )
        self.assertEqual(total, 16)

    def test_overlapping_compartments_rejected(self):
        """Layout JSON with two compartments covering the same cell is rejected."""
        spec = {
            "shelves": 2,
            "columns": 2,
            "compartments": [
                {"shelf_top": 1, "shelf_bottom": 2, "column_index": 1, "slot_count": 1},
                # This one overlaps with the above on (shelf 1, col 1):
                {"shelf_top": 1, "shelf_bottom": 1, "column_index": 1, "slot_count": 1},
                {"shelf_top": 1, "shelf_bottom": 1, "column_index": 2, "slot_count": 1},
                {"shelf_top": 2, "shelf_bottom": 2, "column_index": 2, "slot_count": 1},
            ],
        }
        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-OVR",
                "parent_location_id": self.parent.id,
                "layout_json": json.dumps(spec),
            }
        )
        with self.assertRaises(UserError):
            gen.action_generate()

    def test_compartment_must_have_rack_parent(self):
        """A compartment whose parent isn't a rack is rejected."""
        self._gen_rack("R-T2")
        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-T2")], limit=1)
        # Find a compartment under that rack
        comp = self.env["stock.location"].search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "compartment")],
            limit=1,
        )
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create(
                {
                    "name": "bad-comp",
                    "location_id": comp.id,  # parent is a compartment, not a rack
                    "usage": "view",
                    "wms_location_type": "compartment",
                    "wms_shelf_top": 1,
                    "wms_shelf_bottom": 1,
                    "wms_column_index": 1,
                    "company_id": rack.company_id.id,
                }
            )

    # ─── FIFO helper ────────────────────────────────────────────────────
    def test_fifo_helper(self):
        self._gen_rack("R-FIFO", shelves=2, columns=2, slots=1)
        slots = self.env["stock.location"].search(
            [
                ("wms_location_type", "=", "slot"),
                ("location_id.location_id.wms_rack_code", "=", "R-FIFO"),
            ],
            limit=3,
        )
        self.assertEqual(len(slots), 3)
        # Odoo 19: storable products are type='consu' with is_storable=True.
        product = self.env["product.product"].create(
            {
                "name": "Demo Widget",
                "type": "consu",
                "is_storable": True,
            }
        )
        q1 = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": slots[0].id,
                "quantity": 5,
                "in_date": "2025-01-01 10:00:00",
            }
        )
        q2 = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": slots[1].id,
                "quantity": 5,
                "in_date": "2025-02-01 10:00:00",
            }
        )
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            product.id,
            6,
        )
        self.assertEqual(missing, 0)
        self.assertEqual(plan[0][0], q1)
        self.assertEqual(plan[0][1], 5.0)
        self.assertEqual(plan[1][0], q2)
        self.assertEqual(plan[1][1], 1.0)

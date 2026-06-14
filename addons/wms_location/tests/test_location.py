"""Unit tests for the rack / compartment / slot hierarchy.

Tagged with `wms` so CI can run only our tests via `--test-tags wms`.

The model is: Rack → Compartment (a 2D rectangle on the grid) → Slot.
Shelves and columns are grid coordinates carried on the Compartment, not
separate stock.location rows. A compartment can span multiple shelves,
multiple columns, or both (corner-cabinet shape).
"""

import json

from odoo.exceptions import UserError, ValidationError
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
        # Quick-grid compartments are all single-cell: shelf_top==shelf_bottom
        # and column_left==column_right.
        for c in compartments:
            self.assertEqual(c.wms_shelf_top, c.wms_shelf_bottom)
            self.assertEqual(c.wms_column_left, c.wms_column_right)

    def test_layout_with_vertical_span(self):
        """Layout JSON: 6×3 grid where column 1 has one tall compartment
        covering shelves 1-3, the rest stay single-shelf."""
        compartments = []
        # Column 1: shelves 1-3 merged into one tall compartment (3 slots)
        compartments.append(
            {
                "shelf_top": 1,
                "shelf_bottom": 3,
                "column_left": 1,
                "column_right": 1,
                "slot_count": 3,
            }
        )
        for s in (4, 5, 6):
            compartments.append(
                {
                    "shelf_top": s,
                    "shelf_bottom": s,
                    "column_left": 1,
                    "column_right": 1,
                    "slot_count": 1,
                }
            )
        for s in range(1, 7):
            for c in (2, 3):
                compartments.append(
                    {
                        "shelf_top": s,
                        "shelf_bottom": s,
                        "column_left": c,
                        "column_right": c,
                        "slot_count": 1,
                    }
                )
        spec = {"shelves": 6, "columns": 3, "compartments": compartments}

        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-VSPAN",
                "parent_location_id": self.parent.id,
                "layout_json": json.dumps(spec),
            }
        )
        gen.action_generate()

        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-VSPAN")], limit=1)
        tall = self.env["stock.location"].search(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
                ("wms_column_left", "=", 1),
                ("wms_shelf_top", "=", 1),
            ],
            limit=1,
        )
        self.assertEqual(tall.wms_shelf_bottom, 3, "tall compartment spans shelves 1-3")
        self.assertEqual(tall.wms_column_right, 1, "tall compartment is 1 column wide")
        self.assertEqual(tall.wms_slot_count, 3)

    def test_layout_with_2d_span(self):
        """Layout JSON: 4×4 grid with one corner-cabinet 2x2 block at
        shelves 1-2 × columns 1-2, rest single cells."""
        compartments = [
            # 2x2 corner block
            {
                "shelf_top": 1,
                "shelf_bottom": 2,
                "column_left": 1,
                "column_right": 2,
                "slot_count": 4,
            }
        ]
        # Fill the rest with single cells, skipping the 2x2 region
        for s in range(1, 5):
            for c in range(1, 5):
                if s <= 2 and c <= 2:
                    continue
                compartments.append(
                    {
                        "shelf_top": s,
                        "shelf_bottom": s,
                        "column_left": c,
                        "column_right": c,
                        "slot_count": 1,
                    }
                )
        spec = {"shelves": 4, "columns": 4, "compartments": compartments}
        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-2D",
                "parent_location_id": self.parent.id,
                "layout_json": json.dumps(spec),
            }
        )
        gen.action_generate()

        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-2D")], limit=1)
        corner = self.env["stock.location"].search(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
                ("wms_shelf_top", "=", 1),
                ("wms_column_left", "=", 1),
            ],
            limit=1,
        )
        self.assertEqual(corner.wms_shelf_bottom, 2)
        self.assertEqual(corner.wms_column_right, 2)
        self.assertEqual(corner.wms_slot_count, 4)
        # The corner block's barcode should encode both ranges.
        self.assertEqual(corner.barcode, "R-2D-SH01-02-C01-02")
        # Display name should show both ranges.
        self.assertIn("SH01-02", corner.display_name)
        self.assertIn("C01-02", corner.display_name)
        # Total compartments: 1 corner block + 12 single cells = 13.
        total = self.env["stock.location"].search_count(
            [
                ("location_id", "=", rack.id),
                ("wms_location_type", "=", "compartment"),
            ]
        )
        self.assertEqual(total, 13)

    def test_overlapping_compartments_rejected(self):
        """Layout JSON with two compartments covering the same cell is
        rejected — including 2D overlaps."""
        spec = {
            "shelves": 2,
            "columns": 2,
            "compartments": [
                # 2x2 corner block
                {
                    "shelf_top": 1,
                    "shelf_bottom": 2,
                    "column_left": 1,
                    "column_right": 2,
                    "slot_count": 1,
                },
                # Single cell that overlaps with the block above
                {
                    "shelf_top": 1,
                    "shelf_bottom": 1,
                    "column_left": 1,
                    "column_right": 1,
                    "slot_count": 1,
                },
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

    def test_legacy_column_index_backward_compat(self):
        """Older clients can still post a spec using the legacy
        column_index key — the wizard normalises it to
        column_left/column_right."""
        spec = {
            "shelves": 2,
            "columns": 2,
            "compartments": [
                {"shelf_top": 1, "shelf_bottom": 1, "column_index": 1, "slot_count": 1},
                {"shelf_top": 1, "shelf_bottom": 1, "column_index": 2, "slot_count": 1},
                {"shelf_top": 2, "shelf_bottom": 2, "column_index": 1, "slot_count": 1},
                {"shelf_top": 2, "shelf_bottom": 2, "column_index": 2, "slot_count": 1},
            ],
        }
        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-LEG",
                "parent_location_id": self.parent.id,
                "layout_json": json.dumps(spec),
            }
        )
        gen.action_generate()
        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-LEG")], limit=1)
        comps = self.env["stock.location"].search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "compartment")]
        )
        self.assertEqual(len(comps), 4)
        for c in comps:
            self.assertEqual(c.wms_column_left, c.wms_column_right)

    def test_compartment_must_have_rack_parent(self):
        """A compartment whose parent isn't a rack is rejected."""
        self._gen_rack("R-T2")
        rack = self.env["stock.location"].search([("wms_rack_code", "=", "R-T2")], limit=1)
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
                    "wms_column_left": 1,
                    "wms_column_right": 1,
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

    def test_fifo_helper_falls_back_outside_warehouse_tree(self):
        """When a Trust parks its rack under a custom top-level location
        (e.g. ``Dakshin Vrindavan``) instead of ``WH/Stock``, the strict
        ``child_of lot_stock_id`` lookup misses the stock. The planner
        must fall back to internal locations of the same company so
        Scan Issue doesn't wrongly report STOCK OUT.
        """
        # Build a parent location that's a sibling of WH/Stock, not a
        # descendant — mimics the Trust's "Dakshin Vrindavan" branded
        # top-level location. company_id stays the same so the company
        # guard in the fallback still matches.
        outside_parent = self.env["stock.location"].create(
            {
                "name": "Dakshin Vrindavan (test)",
                "usage": "internal",
                "location_id": False,
                "company_id": self.env.company.id,
            }
        )
        gen = self.env["wms.rack.generator"].create(
            {
                "rack_code": "R-OUT",
                "parent_location_id": outside_parent.id,
                "shelf_count": 1,
                "column_count": 1,
                "default_slot_count": 1,
            }
        )
        gen.action_generate()
        slot = self.env["stock.location"].search(
            [
                ("wms_location_type", "=", "slot"),
                ("location_id.location_id.wms_rack_code", "=", "R-OUT"),
            ],
            limit=1,
        )
        self.assertTrue(slot, "Rack didn't create the slot")
        product = self.env["product.product"].create(
            {
                "name": "Out-of-tree Widget",
                "type": "consu",
                "is_storable": True,
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": slot.id,
                "quantity": 3,
                "in_date": "2025-03-01 10:00:00",
            }
        )
        # Sanity: the strict pass returns no quants because the slot
        # sits outside the warehouse's lot_stock_id subtree.
        strict_hits = self.env["stock.quant"].search_count(
            [
                ("product_id", "=", product.id),
                ("quantity", ">", 0),
                ("location_id.usage", "=", "internal"),
                ("location_id.id", "child_of", self.warehouse.lot_stock_id.id),
            ]
        )
        self.assertEqual(strict_hits, 0, "Slot should be outside WH/Stock")
        # Fallback rescues us.
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            product.id,
            2,
            parent_location_id=self.warehouse.lot_stock_id.id,
        )
        self.assertEqual(missing, 0, "Fallback should have found the out-of-tree quant")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][1], 2.0)

    def test_planner_pools_only_scanned_product(self):
        """Critical #1/#5: the planner pools STRICTLY within the scanned
        product's own template. It never crosses to a same-named SIBLING
        product (which previously could issue a different SKU and unit of
        measure - the wrong-medicine danger). Different physical batches are
        different products; the keeper scans the specific batch to issue."""
        self._gen_rack("R-MED", shelves=1, columns=2, slots=1)
        slots = self.env["stock.location"].search(
            [
                ("wms_location_type", "=", "slot"),
                ("location_id.location_id.wms_rack_code", "=", "R-MED"),
            ],
            limit=2,
        )
        self.assertEqual(len(slots), 2)

        # Batch A: arrived FIRST (in_date Jan), expires LATER (Dec 2027)
        batch_a = (
            self.env["product.template"]
            .create(
                {
                    "name": "Calcium Bolus",
                    "type": "consu",
                    "is_storable": True,
                    "wms_product_kind": "medicine",
                    "wms_expiry_date": "2027-12-31",
                }
            )
            .product_variant_ids[:1]
        )

        # Batch B: arrived LATER (in_date Mar), expires SOONER (Jun 2026)
        batch_b = (
            self.env["product.template"]
            .create(
                {
                    "name": "Calcium Bolus",
                    "type": "consu",
                    "is_storable": True,
                    "wms_product_kind": "medicine",
                    "wms_expiry_date": "2026-06-30",
                }
            )
            .product_variant_ids[:1]
        )

        self.env["stock.quant"].create(
            {
                "product_id": batch_a.id,
                "location_id": slots[0].id,
                "quantity": 10,
                "in_date": "2026-01-01 10:00:00",
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": batch_b.id,
                "location_id": slots[1].id,
                "quantity": 10,
                "in_date": "2026-03-01 10:00:00",
            }
        )

        # Scanning batch A plans ONLY batch A's stock - never the same-named
        # sibling B, even though B expires sooner. Cross-product FEFO was the
        # wrong-medicine danger removed in Critical #1.
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            batch_a.id,
            3,
        )
        self.assertEqual(missing, 0)
        self.assertEqual(len(plan), 1)
        self.assertEqual(
            plan[0][0].product_id.id, batch_a.id, "Must stay within the scanned product"
        )
        self.assertEqual(plan[0][1], 3.0)

        # Scanning batch B plans only B.
        plan_b, missing_b = self.env["stock.location"].find_oldest_quants_for_product(
            batch_b.id,
            3,
        )
        self.assertEqual(missing_b, 0)
        self.assertEqual({q.product_id.id for q, _take in plan_b}, {batch_b.id})

    def test_overuse_cap_fields_default_to_zero(self):
        """``wms_max_per_issue`` and ``wms_daily_cap`` exist on
        product.template, default to 0 (no cap), and can be set
        per-product. Cap enforcement itself lives in the Scan Issue
        wizard (wms_barcode), so we only assert the schema here."""
        p = self.env["product.template"].create(
            {
                "name": "Cap Test",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "tool",
            }
        )
        self.assertEqual(p.wms_max_per_issue, 0.0)
        self.assertEqual(p.wms_daily_cap, 0.0)
        # Admin sets a cap.
        p.write({"wms_max_per_issue": 3.0, "wms_daily_cap": 10.0})
        self.assertEqual(p.wms_max_per_issue, 3.0)
        self.assertEqual(p.wms_daily_cap, 10.0)

    def test_fifo_unchanged_for_non_expiry_kinds(self):
        """Tool / spare / consumable / etc. stay strict FIFO — the FEFO
        path should only kick in for expiry-sensitive kinds."""
        self._gen_rack("R-TOOL", shelves=1, columns=2, slots=1)
        slots = self.env["stock.location"].search(
            [
                ("wms_location_type", "=", "slot"),
                ("location_id.location_id.wms_rack_code", "=", "R-TOOL"),
            ],
            limit=2,
        )
        # Same name, same kind, but kind="tool" (not expiry-sensitive).
        tool_old = (
            self.env["product.template"]
            .create(
                {
                    "name": "Hammer",
                    "type": "consu",
                    "is_storable": True,
                    "wms_product_kind": "tool",
                    # Even with expiry filled (unusual on a tool), it's
                    # the KIND that drives FEFO, not the raw date field —
                    # so it stays FIFO unless the kind is expiry-sensitive.
                }
            )
            .product_variant_ids[:1]
        )
        tool_new = (
            self.env["product.template"]
            .create(
                {
                    "name": "Hammer",
                    "type": "consu",
                    "is_storable": True,
                    "wms_product_kind": "tool",
                }
            )
            .product_variant_ids[:1]
        )

        self.env["stock.quant"].create(
            {
                "product_id": tool_old.id,
                "location_id": slots[0].id,
                "quantity": 5,
                "in_date": "2026-01-01 10:00:00",
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": tool_new.id,
                "location_id": slots[1].id,
                "quantity": 5,
                "in_date": "2026-03-01 10:00:00",
            }
        )
        # FIFO on tool: scan tool_new, planner sees ONLY tool_new's
        # quants (no sibling expansion for non-expiry kinds), picks
        # the only available row.
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            tool_new.id,
            3,
        )
        self.assertEqual(missing, 0)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0].product_id.id, tool_new.id, "Tools must not cross batches")


@tagged("post_install", "-at_install", "wms")
class TestCapabilityBackfill(TransactionCase):
    """3C: the upgrade backfill grants legacy keepers the four daily-work
    capabilities, but must NOT re-grant Manage Catalog (an Admin task) - so an
    upgrade never silently re-widens a keeper's power."""

    def test_backfill_grants_four_caps_not_manage_catalog(self):
        keeper = self.env["res.users"].create(
            {
                "name": "BF Keeper",
                "login": "bf_keeper",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_user").id])],
            }
        )
        self.env["res.users"]._wms_backfill_capabilities()
        keeper.invalidate_recordset()
        granted = set(keeper.all_group_ids.ids)
        for cap in (
            "group_wms_can_scan_receive",
            "group_wms_can_scan_issue",
            "group_wms_can_file_damage",
            "group_wms_can_submit_audit",
        ):
            self.assertIn(
                self.env.ref("wms_location.%s" % cap).id,
                granted,
                "backfill must grant %s" % cap,
            )
        self.assertNotIn(
            self.env.ref("wms_location.group_wms_can_manage_catalog").id,
            granted,
            "backfill must NOT re-grant Manage Catalog to a keeper",
        )


@tagged("post_install", "-at_install", "wms")
class TestFloorZoneBarcodeCollision(TransactionCase):
    """2.5: two parent areas whose names compress to the same 4-char prefix
    must not mint colliding floor-zone barcodes - that would hit the global
    stock.location barcode-unique constraint and roll back the whole batch with
    a cryptic error."""

    def _generate_one_zone(self, parent_name):
        wh = self.env["stock.warehouse"].search([], limit=1)
        parent = self.env["stock.location"].create(
            {
                "name": parent_name,
                "usage": "view",
                "location_id": wh.view_location_id.id,
                "company_id": wh.company_id.id,
            }
        )
        wiz = self.env["wms.floor.zone.generator"].create(
            {
                "warehouse_id": wh.id,
                "parent_location_id": parent.id,
                "zone_prefix": "F",
                "count": 1,
                "start_number": 1,
            }
        )
        wiz.action_generate()
        return self.env["stock.location"].search(
            [("location_id", "=", parent.id), ("wms_location_type", "=", "floor")]
        )

    def test_similar_parent_names_do_not_collide(self):
        z1 = self._generate_one_zone("Pharmacy Building")  # -> "PHAR"
        z2 = self._generate_one_zone("Pharma Store")  # also -> "PHAR"
        self.assertTrue(z1 and z2, "both floor zones must be created without a crash")
        self.assertTrue(z1.barcode and z2.barcode)
        self.assertNotEqual(
            z1.barcode, z2.barcode, "floor-zone barcodes must not collide across parents"
        )

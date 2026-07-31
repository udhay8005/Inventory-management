# -*- coding: utf-8 -*-
"""UAT R4 — storage must live inside the warehouse stock tree.

The defect: the trust's whole structure (234 locations) was built under a
parentless branded location instead of under WH/Stock. Scan Issue still found
the stock, so the system looked healthy — but the weekly audit builds its count
list from ``child_of warehouse.lot_stock_id``, so it generated NO count line
for any of those slots. A floor of medicine could go unverified for months with
nothing on screen to say so.

These tests pin all three halves of the fix: the constraint that refuses the
bad shape, the migration helper that repairs an existing database, and the
audit actually producing a line for stock in a freshly built rack.
"""
from odoo.addons.wms_location.hooks import _rehome_wms_structure
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_tree_integrity")
class TestWarehouseTreeIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.Loc = cls.env["stock.location"]

    def test_01_zone_outside_the_warehouse_tree_is_refused(self):
        """The exact shape that broke the audit must not be creatable."""
        stray_root = self.Loc.create({"name": "TREE Branded Root", "usage": "internal"})
        self.assertFalse(stray_root.location_id, "the stray root has no parent, as in the defect")
        with self.assertRaises(ValidationError):
            self.Loc.create(
                {
                    "name": "TREE Zone Outside",
                    "usage": "internal",
                    "location_id": stray_root.id,
                    "wms_location_type": "zone",
                }
            )

    def test_02_moving_a_good_zone_out_is_refused_too(self):
        """Not just creation — a later re-parent must not smuggle it out."""
        zone = self.Loc.create(
            {
                "name": "TREE Zone Inside",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "zone",
            }
        )
        stray_root = self.Loc.create({"name": "TREE Root 2", "usage": "internal"})
        with self.assertRaises(ValidationError):
            zone.location_id = stray_root.id

    def test_03_untyped_service_locations_are_unaffected(self):
        """The trust-use sink / Damage / Repair-Out locations carry no
        wms_location_type and legitimately live outside the tree — the
        constraint must not touch them."""
        sink = self.Loc.create({"name": "TREE Service Sink", "usage": "internal"})
        self.assertTrue(sink.id, "an untyped top-level location is still allowed")
        trust_use = self.env.ref("wms_location.stock_location_trust_use", raise_if_not_found=False)
        if trust_use:
            self.assertFalse(
                trust_use.wms_location_type,
                "the trust-use sink must stay untyped, or the constraint would fight it",
            )

    def test_04_repair_helper_rehomes_a_stray_tree(self):
        """The migration path: an existing bad database is healed in place."""
        bypass = self.Loc.with_context(wms_skip_tree_check=True)
        stray_root = bypass.create({"name": "TREE Stray Root", "usage": "internal"})
        zone = bypass.create(
            {
                "name": "TREE Stray Zone",
                "usage": "internal",
                "location_id": stray_root.id,
                "wms_location_type": "zone",
            }
        )
        floor = bypass.create(
            {
                "name": "TREE Stray Floor",
                "usage": "internal",
                "location_id": zone.id,
                "wms_location_type": "floor",
            }
        )
        inside = self.Loc.search([("id", "child_of", self.stock.id)])
        self.assertNotIn(zone, inside, "precondition: the zone starts outside the tree")

        _rehome_wms_structure(self.env(context=dict(self.env.context, wms_skip_tree_check=True)))

        inside = self.Loc.search([("id", "child_of", self.stock.id)])
        self.assertIn(zone, inside, "the zone must end up inside the warehouse tree")
        self.assertIn(floor, inside, "children ride along with their parent")
        self.assertEqual(zone.location_id, self.stock, "the zone hangs off WH/Stock")
        self.assertEqual(floor.location_id, zone, "the internal shape is preserved")
        self.assertFalse(stray_root.exists(), "the emptied branded shell is cleaned up")

    def test_04b_rehome_keeps_the_shape_when_an_untyped_area_sits_in_the_middle(self):
        """zone -> (untyped area) -> rack must move as ONE tree.

        Judging "outermost" by the immediate parent would treat the rack as its
        own top — its direct parent is untyped, so not a stray — and re-parent
        it straight to WH/Stock, ripping it out of its zone. Everything would
        then be inside the warehouse but flattened: the audit would count it,
        yet the rack would no longer be in the zone the keeper walks to.
        """
        bypass = self.Loc.with_context(wms_skip_tree_check=True)
        stray_root = bypass.create({"name": "TREE Mid Root", "usage": "internal"})
        zone = bypass.create(
            {
                "name": "TREE Mid Zone",
                "usage": "internal",
                "location_id": stray_root.id,
                "wms_location_type": "zone",
            }
        )
        untyped_area = bypass.create(
            {"name": "TREE Mid Area", "usage": "internal", "location_id": zone.id}
        )
        rack = bypass.create(
            {
                "name": "TREE-MID-RACK",
                "usage": "internal",
                "location_id": untyped_area.id,
                "wms_location_type": "rack",
            }
        )

        _rehome_wms_structure(self.env(context=dict(self.env.context, wms_skip_tree_check=True)))

        inside = self.Loc.search([("id", "child_of", self.stock.id)])
        self.assertIn(zone, inside, "the zone moved into the warehouse tree")
        self.assertIn(rack, inside, "and so did the rack below it")
        self.assertEqual(zone.location_id, self.stock, "the zone is the tree that moved")
        self.assertEqual(
            rack.location_id,
            untyped_area,
            "the rack must still hang off its own area, not be flattened onto WH/Stock",
        )
        self.assertEqual(untyped_area.location_id, zone, "the area is still inside its zone")

    def test_05_audit_counts_stock_in_a_newly_built_rack(self):
        """The user-visible consequence, pinned: stock in a new rack MUST
        appear as a count line. This is what silently failed in UAT."""
        if "wms.audit" not in self.env:
            self.skipTest("wms_reports is not installed in this run")
        zone = self.Loc.create(
            {
                "name": "TREE Audit Zone",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "zone",
            }
        )
        rack = self.Loc.create(
            {
                "name": "TREE-RACK",
                "usage": "internal",
                "location_id": zone.id,
                "wms_location_type": "rack",
                "wms_shelf_count": 1,
                "wms_column_count": 1,
            }
        )
        comp = self.Loc.create(
            {
                "name": "TREE-C01",
                "usage": "internal",
                "location_id": rack.id,
                "wms_location_type": "compartment",
            }
        )
        slot = self.Loc.create(
            {
                "name": "TREE-SL01",
                "usage": "internal",
                "location_id": comp.id,
                "wms_location_type": "slot",
            }
        )
        product = self.env["product.template"].create(
            {"name": "TREE Audit Product", "wms_product_kind": "consumable"}
        )
        self.env["stock.quant"]._update_available_quantity(product.product_variant_id, slot, 7)

        audit = self.env["wms.audit"].create({})
        audit.action_start()
        line = audit.line_ids.filtered(
            lambda ln: ln.location_id == slot and ln.product_id == product.product_variant_id
        )
        self.assertTrue(
            line, "the audit must generate a count line for stock in a newly built rack"
        )
        self.assertEqual(line.expected_qty, 7, "and it must expect the quantity actually there")

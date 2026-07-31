# -*- coding: utf-8 -*-
"""UAT R4 — what the weekly count sheet used to leave out.

The audit built its list from the books (`stock.quant` rows with quantity > 0),
which meant two kinds of error could never be found by counting:

* a slot driven NEGATIVE by an over-issue never appeared, so nobody was ever
  sent to look at it and the wrong figure stayed in the books indefinitely;
* a slot the books call EMPTY was never walked, so stock that was never
  recorded — put away in the wrong slot, returned without a scan, delivered
  straight to a shelf — was undiscoverable. It is missing from the books
  BECAUSE it is unrecorded, and the sheet was built from the books.

These tests pin the fix: negatives are listed, a full walk lists empty slots,
the keeper can add a line for a surprise find, and accepting books it in.
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_audit_coverage")
class TestAuditCoverage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [
            (4, cls.env.ref("wms_location.group_wms_manager").id),
        ]
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        Loc = cls.env["stock.location"]
        cls.zone = Loc.create(
            {
                "name": "AUDIT COV Zone",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "zone",
            }
        )
        cls.slot_a = Loc.create(
            {
                "name": "COV-FLOOR-A",
                "usage": "internal",
                "location_id": cls.zone.id,
                "wms_location_type": "floor",
            }
        )
        cls.slot_b = Loc.create(
            {
                "name": "COV-FLOOR-B",
                "usage": "internal",
                "location_id": cls.zone.id,
                "wms_location_type": "floor",
            }
        )
        cls.product = (
            cls.env["product.template"]
            .create({"name": "COV Rice Sack", "wms_product_kind": "feed"})
            .product_variant_id
        )
        cls.Quant = cls.env["stock.quant"]
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "COV Keeper"})

    def _audit(self, **vals):
        audit = self.env["wms.audit"].create(
            dict({"zone_id": self.zone.id, "storekeeper_id": self.keeper.id}, **vals)
        )
        audit.action_start()
        return audit

    def _line(self, audit, location, product=None):
        return audit.line_ids.filtered(
            lambda ln: ln.location_id == location
            and (ln.product_id == product if product else not ln.product_id)
        )[:1]

    def test_01_negative_stock_is_listed_for_counting(self):
        """A slot at -2 must reach the count sheet — it is precisely the slot
        somebody needs to go and look at."""
        self.Quant.with_context(wms_allow_negative=True)._update_available_quantity(
            self.product, self.slot_a, -2
        )
        self.env.flush_all()

        audit = self._audit()

        line = self._line(audit, self.slot_a, self.product)
        self.assertTrue(line, "a negative slot must appear on the count sheet")
        self.assertEqual(line.expected_qty, -2, "and show the books' figure honestly")

    def test_02_counting_a_negative_slot_corrects_it(self):
        """Counting 5 where the books say -2 restores the truth."""
        self.Quant.with_context(wms_allow_negative=True)._update_available_quantity(
            self.product, self.slot_a, -2
        )
        self.env.flush_all()
        audit = self._audit()
        line = self._line(audit, self.slot_a, self.product)
        line.counted_qty = 5
        audit.action_submit()
        audit.action_review_accept()

        on_hand = sum(
            self.Quant.search(
                [("product_id", "=", self.product.id), ("location_id", "=", self.slot_a.id)]
            ).mapped("quantity")
        )
        self.assertEqual(on_hand, 5, "the slot should now hold what was physically counted")

    def test_03_recorded_scope_does_not_list_empty_slots(self):
        """The default stays quick: only what the books know about."""
        self.Quant._update_available_quantity(self.product, self.slot_a, 3)
        self.env.flush_all()

        audit = self._audit(scope="recorded")

        self.assertTrue(self._line(audit, self.slot_a, self.product))
        self.assertFalse(
            audit.line_ids.filtered(lambda ln: ln.location_id == self.slot_b),
            "an empty slot is not on the quick sheet",
        )

    def test_04_full_walk_lists_the_empty_slot(self):
        """A full walk sends the keeper to every slot in range, so unrecorded
        stock is discoverable at all."""
        self.Quant._update_available_quantity(self.product, self.slot_a, 3)
        self.env.flush_all()

        audit = self._audit(scope="full")

        empty_line = self._line(audit, self.slot_b)
        self.assertTrue(empty_line, "the empty slot must be on the walk")
        self.assertFalse(empty_line.product_id, "with no product — the books know of none")
        self.assertEqual(empty_line.expected_qty, 0)

    def test_05_finding_stock_in_an_empty_slot_books_it_in(self):
        """The whole point: goods nobody recorded get discovered and booked."""
        audit = self._audit(scope="full")
        line = self._line(audit, self.slot_b)
        line.product_id = self.product
        line.counted_qty = 7

        self.assertEqual(audit.found_count, 1, "it counts as an unrecorded find")
        audit.action_submit()
        audit.action_review_accept()

        on_hand = sum(
            self.Quant.search(
                [("product_id", "=", self.product.id), ("location_id", "=", self.slot_b.id)]
            ).mapped("quantity")
        )
        self.assertEqual(on_hand, 7, "the found stock is now on the books")

    def test_06_keeper_can_add_a_line_for_a_surprise_find(self):
        """Even on the quick sheet, something found off-list can be written
        down — that is how a real count works."""
        self.Quant._update_available_quantity(self.product, self.slot_a, 3)
        self.env.flush_all()
        audit = self._audit(scope="recorded")

        added = self.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": self.slot_b.id,
                "product_id": self.product.id,
                "counted_qty": 4,
            }
        )
        self.assertTrue(added.is_found_line, "a hand-added line is marked as such")

        audit.action_submit()
        audit.action_review_accept()

        on_hand = sum(
            self.Quant.search(
                [("product_id", "=", self.product.id), ("location_id", "=", self.slot_b.id)]
            ).mapped("quantity")
        )
        self.assertEqual(on_hand, 4)

    def test_07_a_count_must_name_what_was_counted(self):
        """ "3 of something" is not a count."""
        audit = self._audit(scope="full")
        line = self._line(audit, self.slot_b)
        with self.assertRaises(ValidationError):
            line.counted_qty = 3

    def test_08_walked_and_empty_is_recorded_without_adjusting_anything(self):
        """A product-less line left at zero means "I went, it was empty" — it
        must not be treated as a variance or book anything."""
        audit = self._audit(scope="full")
        empty_line = self._line(audit, self.slot_b)
        self.assertTrue(empty_line, "the empty slot is on the walk")
        self.assertEqual(audit.variance_count, 0, "walking an empty slot is not a variance")
        audit.action_submit()
        audit.action_review_accept()
        self.assertFalse(
            self.Quant.search([("location_id", "=", self.slot_b.id)]),
            "nothing should have been created for a slot confirmed empty",
        )
        self.assertEqual(audit.state, "reviewed")

    def test_09_area_filter_keeps_a_full_walk_practical(self):
        """One zone a week, not the whole warehouse in one impossible sweep."""
        other_zone = self.env["stock.location"].create(
            {
                "name": "AUDIT COV Other Zone",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "zone",
            }
        )
        other_slot = self.env["stock.location"].create(
            {
                "name": "COV-OTHER-FLOOR",
                "usage": "internal",
                "location_id": other_zone.id,
                "wms_location_type": "floor",
            }
        )

        audit = self._audit(scope="full", zone_id=self.zone.id)

        walked = audit.line_ids.mapped("location_id")
        self.assertIn(self.slot_b, walked, "slots in the chosen area are walked")
        self.assertNotIn(other_slot, walked, "slots elsewhere are not")

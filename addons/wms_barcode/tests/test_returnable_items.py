"""F3 — Returnable items: expected-return SLA + Scan Return marking.

Covers the wms_location + wms_barcode side of F3 (the wms_reports cron /
Returns-due report are tested in wms_reports):

  * a returnable product (tool) seeds expected_return_days from its kind
    (14 days), a non-returnable product (feed) stays at 0;
  * issuing a returnable product stamps the picking's
    wms_expected_return_date = today + the product's expected_return_days,
    leaving wms_returned False;
  * issuing a NON-returnable product carries no expected-return date;
  * when expected_return_days is 0 the global System Parameter
    wms_reports.default_return_days is used as the fallback;
  * Scan Return of the tool marks the matched outstanding issue picking
    wms_returned=True (best-effort, oldest expected-return first);
  * a reversed (undone) issue is excluded from the return match (mirrors
    the overdue cron's wms_reversed_by_id IS NULL guard).
"""

from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_returnable")
class TestReturnableItems(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "UAT Keeper RET"})

        # A returnable tool: kind 'tool' seeds expected_return_days = 14.
        cls.tool = cls.env["product.product"].create(
            {
                "name": "RET-TEST Drill",
                "type": "consu",
                "is_storable": True,
                "barcode": "RETTOOL001",
                "wms_product_kind": "tool",
            }
        )
        # A non-returnable feed: kind 'feed' -> not returnable, 0 days.
        cls.feed = cls.env["product.product"].create(
            {
                "name": "RET-TEST Bran",
                "type": "consu",
                "is_storable": True,
                "barcode": "RETFEED001",
                "wms_product_kind": "feed",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.tool, cls.stock, 50.0)
        # Feed is a perishable kind -> lot-tracked under v20; seed it with a lot.
        cls.feed_lot = cls.env["stock.lot"].create(
            {
                "name": "RET-FEED-LOT",
                "product_id": cls.feed.id,
                "company_id": cls.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.feed, cls.stock, 50.0, lot_id=cls.feed_lot
        )

        # A floor zone so Scan Return's _auto_assign_slot has a destination
        # to land on. A fresh --without-demo warehouse has no rack slots or
        # floor zones, so the return receipt would otherwise raise a UserError.
        # Mirrors the fixture in test_receipt_photo.py.
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "RET-TEST Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    # ------------------------------------------------------------------
    # Product-level kind seeding (wms_location)
    # ------------------------------------------------------------------
    def test_tool_seeds_return_days(self):
        self.assertTrue(self.tool.wms_is_returnable, "a Tool must default returnable")
        self.assertEqual(
            self.tool.expected_return_days,
            14,
            "a returnable Tool should seed expected_return_days = 14 from its kind",
        )

    def test_feed_has_no_return_days(self):
        self.assertFalse(self.feed.wms_is_returnable, "Feed must default NOT returnable")
        self.assertEqual(
            self.feed.expected_return_days,
            0,
            "a non-returnable Feed should keep expected_return_days = 0",
        )

    def test_product_product_related_mirror(self):
        """The product.product related mirror exposes the template value."""
        self.assertEqual(
            self.tool.expected_return_days,
            self.tool.product_tmpl_id.expected_return_days,
            "product.product.expected_return_days must mirror the template",
        )

    def test_admin_override_survives(self):
        """The compute only seeds; an admin override per product persists."""
        tmpl = self.env["product.template"].create(
            {"name": "RET Override Tool", "wms_product_kind": "tool"}
        )
        self.assertEqual(tmpl.expected_return_days, 14)
        tmpl.expected_return_days = 30
        self.assertEqual(
            tmpl.expected_return_days,
            30,
            "an admin override of expected_return_days must persist",
        )

    # ------------------------------------------------------------------
    # Scan Issue stamping (wms_barcode)
    # ------------------------------------------------------------------
    def _issue(self, barcode, qty=1.0):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": barcode,
                "taken_by": "Test Taker",
                "ordered_by": "Test Orderer",
                "usage_note": "returnable test",
                "storekeeper_id": self.keeper.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        return wiz.picking_id

    def test_issue_returnable_stamps_expected_return_date(self):
        picking = self._issue("RETTOOL001")
        self.assertEqual(
            picking.wms_expected_return_date,
            date.today() + timedelta(days=14),
            "issuing a returnable Tool must stamp today + expected_return_days",
        )
        self.assertFalse(
            picking.wms_returned,
            "wms_returned must start False on a fresh returnable issue",
        )

    def test_issue_non_returnable_has_no_date(self):
        picking = self._issue("RETFEED001")
        self.assertFalse(
            picking.wms_expected_return_date,
            "a non-returnable issue must carry no expected-return date",
        )

    def test_issue_uses_global_fallback_when_days_zero(self):
        """A returnable product with expected_return_days == 0 falls back
        to the global System Parameter wms_reports.default_return_days."""
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.default_return_days", "5")
        spare = self.env["product.product"].create(
            {
                "name": "RET Fallback Spare",
                "type": "consu",
                "is_storable": True,
                "barcode": "RETSPARE001",
                "wms_product_kind": "spare",
            }
        )
        # Force the per-product SLA to 0 so the fallback is exercised.
        spare.expected_return_days = 0
        self.env["stock.quant"]._update_available_quantity(spare, self.stock, 10.0)
        picking = self._issue("RETSPARE001")
        self.assertEqual(
            picking.wms_expected_return_date,
            date.today() + timedelta(days=5),
            "a 0-day returnable product must use the global default fallback",
        )

    # ------------------------------------------------------------------
    # Scan Return marking (wms_barcode)
    # ------------------------------------------------------------------
    def _return(self, barcode, qty=1.0, condition="good"):
        wiz = self.env["wms.scan.receipt"].create(
            {
                "warehouse_id": self.wh.id,
                "is_return": True,
                "qc_passed": True,
                "storekeeper_id": self.keeper.id,
                "return_condition": condition,
            }
        )
        wiz.last_scan = barcode
        wiz.action_process_scan()
        wiz.action_validate()
        return wiz.picking_id

    def test_scan_return_records_condition_and_date(self):
        """Scan Return records HOW the item came back (condition) and WHEN
        (actual return date) on the original issue, not just a boolean."""
        issue = self._issue("RETTOOL001")
        self._return("RETTOOL001", condition="good")
        issue.invalidate_recordset(
            ["wms_returned", "wms_return_condition", "wms_actual_return_date"]
        )
        self.assertTrue(issue.wms_returned)
        self.assertEqual(issue.wms_return_condition, "good")
        self.assertEqual(issue.wms_actual_return_date, date.today())

    def test_damaged_return_records_condition(self):
        """A damaged / needs-repair return records the condition on the issue
        (and routes to managers — best-effort, must not raise)."""
        issue = self._issue("RETTOOL001")
        self._return("RETTOOL001", condition="damaged")
        issue.invalidate_recordset(["wms_return_condition"])
        self.assertEqual(
            issue.wms_return_condition,
            "damaged",
            "a damaged return must record the condition on the issue picking",
        )

    def test_scan_return_marks_matched_picking(self):
        issue = self._issue("RETTOOL001")
        self.assertFalse(issue.wms_returned)
        self._return("RETTOOL001")
        issue.invalidate_recordset(["wms_returned"])
        self.assertTrue(
            issue.wms_returned,
            "Scan Return of the tool must mark the matched issue wms_returned",
        )

    def test_scan_return_clears_oldest_first(self):
        """When two returnable issues are open, the return clears the one
        with the earliest expected-return date first."""
        older = self._issue("RETTOOL001")
        newer = self._issue("RETTOOL001")
        # Force a clear ordering independent of id.
        older.wms_expected_return_date = date.today()
        newer.wms_expected_return_date = date.today() + timedelta(days=30)
        self._return("RETTOOL001")
        older.invalidate_recordset(["wms_returned"])
        newer.invalidate_recordset(["wms_returned"])
        self.assertTrue(older.wms_returned, "the earliest-due issue must be cleared first")
        self.assertFalse(newer.wms_returned, "a single return must not clear two issues")

    def test_reversed_issue_excluded_from_match(self):
        """A reversed (undone) issue must not be matched by Scan Return —
        the same wms_reversed_by_id IS NULL guard the overdue cron uses."""
        issue = self._issue("RETTOOL001")
        # Simulate the undo having pointed wms_reversed_by_id at a transfer.
        reverse = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh.int_type_id.id,
                "location_id": self.stock.id,
                "location_dest_id": self.stock.id,
                "origin": "Undo: %s" % issue.name,
                "wms_is_undo": True,
            }
        )
        issue.wms_reversed_by_id = reverse.id
        self._return("RETTOOL001")
        issue.invalidate_recordset(["wms_returned"])
        self.assertFalse(
            issue.wms_returned,
            "a reversed issue must be excluded from the Scan Return match",
        )

    def test_no_match_leaves_nothing_changed(self):
        """A return for a product with no outstanding returnable issue does
        nothing (the item just stays absent from the report)."""
        # Issue + immediately return the tool so its issue is already cleared.
        issue = self._issue("RETTOOL001")
        self._return("RETTOOL001")
        issue.invalidate_recordset(["wms_returned"])
        self.assertTrue(issue.wms_returned)
        # A second return finds no open issue — must not raise, must not
        # re-flag the already-returned picking (idempotent / safe no-op).
        before = issue.wms_returned
        self._return("RETTOOL001")
        issue.invalidate_recordset(["wms_returned"])
        self.assertEqual(issue.wms_returned, before)

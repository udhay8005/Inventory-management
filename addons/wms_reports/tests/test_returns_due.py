"""F3 — returnable-items overdue cron + Returns-due SQL report (wms_reports).

This proves the wms_reports half of F3:

  * the daily cron ``wms.returns.cron._cron_check_overdue_returns`` notifies WMS
    Managers exactly once when a returnable issue is past its expected return
    date, and stays SILENT when nothing is overdue / the item has come back /
    the issue was reversed (Undone);
  * the ``wms.returns.due.report`` SQL view lists outstanding returnable issues
    with the right ``days_overdue`` and ``state``, and excludes returned /
    reversed rows.

The picking fields ``wms_expected_return_date`` / ``wms_returned`` are stamped
by the sibling wms_barcode Scan-Issue commit; here we drive a real Scan Issue
and then set those fields directly to isolate the wms_reports logic under test.
``notify_wms_managers`` is patched on the cron module (the import target) so we
assert delivery without touching the mail stack — mirrors the gdrive tests.
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.wms_reports.models import wms_returns_due as returns_module
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_returns")
class TestReturnsDue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "RET Keeper"})
        cls.dept = cls.env.ref("wms_location.dept_gaushala")
        # A returnable kind (tool) so wms_is_returnable is True by default.
        cls.product = cls.env["product.product"].create(
            {
                "name": "RET Spanner",
                "type": "consu",
                "is_storable": True,
                "barcode": "RETTEST0001",
                "wms_product_kind": "tool",
            }
        )
        cls.product.standard_price = 100.0
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 50.0)
        # Pin the company timezone so the report's company-tz "today" matches the
        # UTC base _stamp() uses below — makes days_overdue deterministic at any
        # wall-clock hour, and exercises the new company-tz code path.
        cls.env.company.partner_id.tz = "UTC"
        cls.env.flush_all()

    def _issue(self, qty=1.0):
        """Drive a real Scan Issue and return its picking."""
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": "RETTEST0001",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "returns test",
                "storekeeper_id": self.keeper.id,
                "department_id": self.dept.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        return wiz.picking_id

    def _stamp(self, picking, days_offset, returned=False):
        """Stamp the F3 issue fields the sibling wizard commit sets."""
        # UTC base to match the report's company-tz (UTC) reference, so the
        # day-count assertions are deterministic at any hour.
        due = fields.Date.today() + timedelta(days=days_offset)
        picking.write({"wms_expected_return_date": due, "wms_returned": returned})
        self.env.flush_all()

    def _mark_reversed(self, picking):
        """Simulate an Undo by setting wms_reversed_by_id (the cron/report key
        is simply that it is non-NULL). Driving the full action_wms_undo flow
        would couple this report test to the undo window + reservation rails,
        which is the sibling commit's concern, not the report's."""
        sentinel = self.env["stock.picking"].create(
            {
                "picking_type_id": picking.picking_type_id.id,
                "location_id": picking.location_dest_id.id,
                "location_dest_id": picking.location_id.id,
                "origin": "Undo: %s" % (picking.name or ""),
                "wms_is_undo": True,
            }
        )
        picking.write({"wms_reversed_by_id": sentinel.id})
        self.env.flush_all()

    def _run_cron(self):
        with patch.object(returns_module, "notify_wms_managers") as notify:
            self.env["wms.returns.cron"]._cron_check_overdue_returns()
        return notify

    # ---- cron --------------------------------------------------------------

    def test_overdue_notifies_once(self):
        picking = self._issue()
        self._stamp(picking, -1)  # expected back yesterday
        notify = self._run_cron()
        self.assertEqual(notify.call_count, 1, "one overdue picking should notify exactly once")

    def test_multiple_overdue_single_notice(self):
        self._stamp(self._issue(), -2)
        self._stamp(self._issue(), -5)
        notify = self._run_cron()
        # Deduped into a single digest notice, not one per picking.
        self.assertEqual(notify.call_count, 1)

    def test_not_overdue_is_silent(self):
        picking = self._issue()
        self._stamp(picking, +3)  # still within the window
        notify = self._run_cron()
        notify.assert_not_called()

    def test_returned_is_silent(self):
        picking = self._issue()
        self._stamp(picking, -3, returned=True)  # overdue date but already back
        notify = self._run_cron()
        notify.assert_not_called()

    def test_no_due_date_is_silent(self):
        # A normal (non-returnable) issue never gets a return date stamped.
        self._issue()
        notify = self._run_cron()
        notify.assert_not_called()

    def test_reversed_issue_never_overdue(self):
        picking = self._issue()
        self._stamp(picking, -4)
        self._mark_reversed(picking)
        notify = self._run_cron()
        notify.assert_not_called()

    # ---- SQL report --------------------------------------------------------

    def _report_rows(self, picking):
        return self.env["wms.returns.due.report"].search([("picking_id", "=", picking.id)])

    def test_report_lists_overdue_row(self):
        picking = self._issue(2.0)
        self._stamp(picking, -3)
        rows = self._report_rows(picking)
        self.assertTrue(rows, "an outstanding overdue issue must appear in the report")
        self.assertEqual(rows[0].state, "overdue")
        self.assertEqual(rows[0].days_overdue, 3)
        self.assertEqual(rows[0].product_id, self.product)
        self.assertEqual(rows[0].department_id, self.dept)

    def test_report_due_soon_state(self):
        picking = self._issue()
        self._stamp(picking, +2)
        rows = self._report_rows(picking)
        self.assertTrue(rows)
        self.assertEqual(rows[0].state, "due_soon")
        self.assertEqual(rows[0].days_overdue, -2)

    def test_report_excludes_returned(self):
        picking = self._issue()
        self._stamp(picking, -3, returned=True)
        self.assertFalse(self._report_rows(picking))

    def test_report_excludes_reversed(self):
        picking = self._issue()
        self._stamp(picking, -3)
        self._mark_reversed(picking)
        self.assertFalse(self._report_rows(picking))

    def test_report_readable_by_keeper(self):
        """3E: the read-only Returns-due report is keeper-visible - the people
        who do the returns can self-serve the due/overdue list."""
        keeper_user = self.env["res.users"].create(
            {
                "name": "RET ACL Keeper",
                "login": "ret_acl_keeper",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_user").id])],
            }
        )
        self.assertTrue(
            self.env["ir.model.access"]
            .with_user(keeper_user)
            .check("wms.returns.due.report", "read", raise_exception=False),
            "a keeper (group_wms_user) must be able to read the Returns-due report",
        )

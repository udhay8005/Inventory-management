"""Cycle-Count-Due fields: registry consistency + behaviour.

Regression guard for the registry-load warning

    stock.location: inconsistent 'compute_sudo'/'store' for computed fields
    wms_last_counted, wms_days_since_count

caused by both fields sharing ONE compute method while differing in `store`
and `compute_sudo`. The fix splits them into two distinct compute methods.
This test pins (a) the two fields use different compute methods with the
intended store/compute_sudo flags, and (b) the count-age values + the
wms.cycle.count.due SQL view still behave as before.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_cycle_count")
class TestCycleCountFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        wh = cls.env["stock.warehouse"].search([], limit=1)
        # A floor zone is a stockable WMS location with no compartment/slot
        # hierarchy constraint, so quants can land on it directly.
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "Cycle Count Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Cycle Count Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )

    def test_count_fields_are_consistent_and_distinct(self):
        """The two fields must NOT share a compute method, and each must keep
        its intended store/compute_sudo — this is what silences the warning."""
        Location = self.env["stock.location"]
        f_last = Location._fields["wms_last_counted"]
        f_days = Location._fields["wms_days_since_count"]

        # Distinct compute methods is the whole point of the fix.
        self.assertNotEqual(
            f_last.compute,
            f_days.compute,
            "wms_last_counted and wms_days_since_count must use DISTINCT compute "
            "methods, else Odoo warns about inconsistent compute_sudo/store.",
        )
        # Stored + sudo on the date column; on-read + non-sudo on the delta.
        self.assertTrue(f_last.store)
        self.assertTrue(f_last.compute_sudo)
        self.assertFalse(f_days.store)
        self.assertFalse(f_days.compute_sudo)

    def test_count_age_reflects_quant_in_date(self):
        """wms_last_counted tracks the latest quant date; days_since_count is
        today minus that date, fresh on every read."""
        self.env["stock.quant"]._update_available_quantity(self.product, self.floor, 5.0)
        in_date = fields.Datetime.now() - timedelta(days=40)
        self.env["stock.quant"].search(
            [("product_id", "=", self.product.id), ("location_id", "=", self.floor.id)]
        ).write({"in_date": in_date})
        self.floor.invalidate_recordset(["wms_last_counted", "wms_days_since_count"])

        self.assertEqual(self.floor.wms_last_counted, in_date)
        # ~40 days; allow for the clock ticking during the test run.
        self.assertIn(self.floor.wms_days_since_count, (39, 40))

    def test_non_stockable_location_reads_zero(self):
        """A view/rack location is not counted: null date, zero delta."""
        view_loc = self.env["stock.location"].search(
            [("wms_location_type", "=", False)], limit=1
        ) or self.env.ref("stock.stock_location_locations")
        self.assertFalse(view_loc.wms_last_counted)
        self.assertEqual(view_loc.wms_days_since_count, 0)

    def test_due_view_lists_stale_floor(self):
        """The wms.cycle.count.due SQL view (and the weekly cron's recompute)
        still flag a floor stale > 30 days."""
        self.env["stock.quant"]._update_available_quantity(self.product, self.floor, 5.0)
        self.env["stock.quant"].search(
            [("product_id", "=", self.product.id), ("location_id", "=", self.floor.id)]
        ).write({"in_date": fields.Datetime.now() - timedelta(days=45)})
        # The cron recomputes + flushes the stored date the view reads.
        self.env["wms.cycle.count.cron"].run_weekly_reminder()

        due = self.env["wms.cycle.count.due"].search([("location_id", "=", self.floor.id)])
        self.assertTrue(due, "a floor stale > 30 days must appear in Cycle Count Due")
        self.assertGreater(due.days_since_count, 30)

"""Wave 2 #7 — Occupancy-over-time snapshots + FEFO compliance.

Two pieces under one feature:

  * ``wms.occupancy.snapshot`` — the daily cron ``_cron_capture`` writes one
    stored row per storage location for today, idempotently.
  * ``wms.fefo.compliance`` — an SQL view over done Scan-Issue move lines that
    scores whether the issued lot was the earliest-expiry one available.

The FEFO test builds a real done outbound move (the only way to get a done
``stock.move.line`` carrying a lot on a Scan Issue picking) following the
project's standard test recipe: confirm, drop the auto move lines, create one
explicit move line with the lot + qty + locations, set ``picked``, then
``_action_done``.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestOccupancyFefo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.customers = cls.env.ref("stock.stock_location_customers")

        # A rack-slot storage location with a soft capacity, so occupancy_pct
        # is a meaningful non-zero number.
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "OCC Slot",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",  # floor: a standalone storable area
                "wms_capacity_units": 100.0,
            }
        )

        # Medicine kind => auto lot-tracked with expiry (wms_perishable.create).
        cls.prod = cls.env["product.product"].create(
            {
                "name": "OCCFEFO Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "OCCFEFO01",
                "standard_price": 3.0,
            }
        )

    # ---- Occupancy snapshot cron -----------------------------------------
    def test_cron_capture_creates_rows_idempotently(self):
        Snap = self.env["wms.occupancy.snapshot"]
        # Put 40 units on hand at the slot so on_hand / capacity = 40%.
        lot = self.env["stock.lot"].create(
            {
                "name": "OCC-LOT-1",
                "product_id": self.prod.id,
                "company_id": self.env.company.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.prod, self.slot, 40, lot_id=lot)
        self.env.flush_all()

        today = fields.Date.context_today(Snap)
        count = Snap._cron_capture()
        self.assertGreaterEqual(count, 1, "cron should snapshot at least the seeded slot")

        rows = Snap.search([("snapshot_date", "=", today), ("location_id", "=", self.slot.id)])
        self.assertEqual(len(rows), 1, "exactly one snapshot row for the slot today")
        row = rows[0]
        self.assertEqual(row.on_hand, 40.0)
        self.assertEqual(row.capacity, 100.0)
        self.assertAlmostEqual(row.occupancy_pct, 40.0, places=2)
        self.assertEqual(row.location_kind, "floor")
        self.assertEqual(row.distinct_products, 1)

        # Idempotent: a same-day re-run updates in place, never duplicates.
        Snap._cron_capture()
        rows_after = Snap.search(
            [("snapshot_date", "=", today), ("location_id", "=", self.slot.id)]
        )
        self.assertEqual(len(rows_after), 1, "re-running the cron must not duplicate the day's row")

    # ---- FEFO compliance view --------------------------------------------
    def _make_done_issue(self, lot, qty):
        """Build + complete a Scan-Issue outbound move drawing ``lot``.

        Mirrors the project's done-move recipe so the resulting move line is
        state='done', carries the lot, and hangs off a wms_is_scan_issue
        picking (which the FEFO view filters on). A storekeeper is set so the
        audit-triplet CHECK on done WMS pickings is satisfied.
        """
        keeper = self.env["wms.storekeeper"].search([], limit=1)
        if not keeper:
            keeper = self.env["wms.storekeeper"].create({"name": "OCC Keeper"})
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh.out_type_id.id,
                "location_id": self.slot.id,
                "location_dest_id": self.customers.id,
                "origin": "Barcode FIFO issue",
                "wms_is_scan_issue": True,
                "wms_storekeeper_id": keeper.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "description_picking": self.prod.display_name,
                "product_id": self.prod.id,
                "product_uom_qty": qty,
                "product_uom": self.prod.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.slot.id,
                "location_dest_id": self.customers.id,
            }
        )
        move._action_confirm()
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.prod.id,
                "lot_id": lot.id,
                "quantity": qty,
                "location_id": self.slot.id,
                "location_dest_id": self.customers.id,
            }
        )
        move.picked = True
        move._action_done()
        return picking

    def test_fefo_view_returns_row_for_issue(self):
        Fefo = self.env["wms.fefo.compliance"]
        now = fields.Datetime.now()

        # Two batches: a short-dated one (earliest expiry, still on shelf) and a
        # long-dated one we will wrongly issue from -> a FEFO violation.
        short_lot = self.env["stock.lot"].create(
            {
                "name": "OCC-SHORT",
                "product_id": self.prod.id,
                "company_id": self.env.company.id,
                "expiration_date": now + timedelta(days=30),
            }
        )
        long_lot = self.env["stock.lot"].create(
            {
                "name": "OCC-LONG",
                "product_id": self.prod.id,
                "company_id": self.env.company.id,
                "expiration_date": now + timedelta(days=400),
            }
        )
        # Stock both batches so the short-dated one is "available" at issue time.
        self.env["stock.quant"]._update_available_quantity(
            self.prod, self.slot, 10, lot_id=short_lot
        )
        self.env["stock.quant"]._update_available_quantity(
            self.prod, self.slot, 10, lot_id=long_lot
        )
        self.env.flush_all()

        # Issue from the LONG (later-expiry) lot -> should score non-compliant
        # because the short-dated batch was still on the shelf.
        self._make_done_issue(long_lot, 3)
        self.env.flush_all()

        rows = Fefo.search([("product_id", "=", self.prod.id)])
        self.assertTrue(rows, "FEFO view must return a row for the seeded scan issue")
        violation = rows.filtered(lambda r: r.lot_id == long_lot)
        self.assertEqual(len(violation), 1, "exactly one row for the long-lot issue")
        row = violation[0]
        self.assertEqual(row.quantity, 3.0)
        self.assertTrue(row.month, "month bucket must be populated for the rate graph")
        self.assertFalse(
            row.compliant,
            "issuing the later-expiry lot while a shorter-dated one was on hand "
            "must score as a FEFO violation",
        )

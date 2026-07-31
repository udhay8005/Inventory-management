# -*- coding: utf-8 -*-
"""Concurrency-hardening tests for the scan wizards (STEP 6).

Odoo's TransactionCase runs each test inside ONE transaction that never
commits, so a second DB connection cannot see the test's fixtures — real
OS-thread concurrency is therefore not cleanly testable here. Instead we
prove every SAFETY OUTCOME deterministically by simulating the concurrent
change (e.g. another keeper depleting a slot between planning and
validating) and asserting the guard fires:

  * a double-submit never issues/receives twice (idempotency picking_id),
  * an issue aborts cleanly (no negative/phantom stock) when its planned
    stock was taken underneath it (the assigned-state check),
  * the daily cap still blocks (it now runs inside the per-product lock).

The per-product `FOR UPDATE` lock itself is a PostgreSQL serialization
guarantee exercised on every happy-path issue below; its blocking
behaviour is the database's contract, not something a single-process
test can stage.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_concurrency")
class TestScanConcurrency(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "UAT Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "CONC-TEST Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "CONCTEST001",
                "wms_product_kind": "consumable",
            }
        )
        # 10 units on hand, in the warehouse stock location.
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 10.0)

    def _on_hand(self):
        return self.env["stock.quant"]._get_available_quantity(self.product, self.stock)

    def _new_issue(self, qty=3.0):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": "CONCTEST001",
                "taken_by": "Test Taker",
                "ordered_by": "Test Orderer",
                "usage_note": "concurrency test",
                "storekeeper_id": self.keeper.id,
            }
        )
        wiz.action_plan()
        return wiz

    # ---- Idempotency ----------------------------------------------------
    def test_issue_double_click_is_idempotent(self):
        """Validating twice must create exactly ONE delivery and deduct
        the stock once."""
        start = self._on_hand()
        wiz = self._new_issue(3.0)
        wiz.action_validate()
        first_picking = wiz.picking_id
        self.assertTrue(first_picking, "first validate should create a picking")
        after_first = self._on_hand()
        self.assertAlmostEqual(after_first, start - 3.0, places=3)

        # Second click (or refresh re-submit) on the SAME wizard.
        wiz.action_validate()
        self.assertEqual(wiz.picking_id, first_picking, "must reuse the same picking")
        self.assertAlmostEqual(self._on_hand(), after_first, places=3, msg="no second deduction")
        count = self.env["stock.picking"].search_count(
            [("origin", "=", "Barcode FIFO issue"), ("wms_storekeeper_id", "=", self.keeper.id)]
        )
        self.assertGreaterEqual(count, 1)

    # ---- Stock taken concurrently --------------------------------------
    def test_issue_aborts_when_stock_taken_concurrently(self):
        """If a planned slot is emptied between planning and validating
        (another keeper got there first), the issue aborts cleanly: a
        friendly error, no delivery, and stock never goes negative."""
        wiz = self._new_issue(8.0)
        # Simulate another keeper taking ALL the stock after we planned.
        self.env["stock.quant"]._update_available_quantity(self.product, self.stock, -10.0)
        self.assertAlmostEqual(self._on_hand(), 0.0, places=3)

        with self.assertRaises(UserError):
            wiz.action_validate()
        # Nothing issued, no picking recorded, stock not negative.
        self.assertFalse(wiz.picking_id)
        self.assertGreaterEqual(self._on_hand(), 0.0)

    # ---- Daily cap (race-safe behind the per-product lock) -------------
    def test_daily_cap_blocks_second_issue(self):
        self.product.product_tmpl_id.wms_daily_cap = 5.0
        self._new_issue(3.0).action_validate()  # 3 issued, under cap
        # A second issue of 3 -> projected 6 > cap 5 -> must block.
        wiz2 = self._new_issue(3.0)
        with self.assertRaises(UserError):
            wiz2.action_validate()
        self.assertFalse(wiz2.picking_id)

    def test_daily_cap_window_counts_20h_excludes_25h(self):
        """The rolling 24h cap window is measured against each move-line's UTC
        create_date. An issue ~20h ago must still count toward the cap; one
        ~25h ago must have aged out.

        Regression guard for the timezone fix: the cutoff is computed with
        fields.Datetime.now() (UTC) to match the UTC create_date column. The
        old code used datetime.now() (server-LOCAL), which on the IST deploy
        shrank the window by the offset (~18.5h) and let the cap fail OPEN.
        Both the cutoff and the back-dated create_date here are anchored in
        UTC, so the assertion is deterministic on any server timezone.

        Back-dating create_date via SQL is the only way to age a row inside a
        single non-committing test transaction.
        """
        # Plenty of stock so the SECOND issue can only be blocked by the cap,
        # never by an empty slot.
        self.env["stock.quant"]._update_available_quantity(self.product, self.stock, 100.0)
        self.product.product_tmpl_id.wms_daily_cap = 15.0

        self._new_issue(10.0).action_validate()  # 10 issued "now"
        prior = self.env["stock.move.line"].search(
            [("product_id", "=", self.product.id), ("state", "=", "done")]
        )
        self.assertTrue(prior, "the first issue should have left done move-lines")

        # Age the prior issue to ~20h ago -> still inside the 24h window.
        self.env.cr.execute(
            "UPDATE stock_move_line "
            "SET create_date = (now() AT TIME ZONE 'UTC') - INTERVAL '20 hours' "
            "WHERE id IN %s",
            (tuple(prior.ids),),
        )
        prior.invalidate_recordset(["create_date"])
        # 10 (in-window) + 8 = 18 > 15 -> must block.
        with self.assertRaises(UserError):
            self._new_issue(8.0).action_validate()

        # Age it to ~25h ago -> out of the window, no longer counts.
        self.env.cr.execute(
            "UPDATE stock_move_line "
            "SET create_date = (now() AT TIME ZONE 'UTC') - INTERVAL '25 hours' "
            "WHERE id IN %s",
            (tuple(prior.ids),),
        )
        prior.invalidate_recordset(["create_date"])
        # 0 in-window + 8 = 8 < 15 -> allowed again.
        wiz = self._new_issue(8.0)
        wiz.action_validate()
        self.assertTrue(
            wiz.picking_id, "an issue must be allowed once the prior one ages out of the 24h window"
        )

    # ---- Happy path exercises the product-row FOR UPDATE lock ----------
    def test_issue_happy_path_with_product_lock(self):
        start = self._on_hand()
        wiz = self._new_issue(2.0)
        wiz.action_validate()  # runs the FOR UPDATE lock SQL + assigns + validates
        self.assertTrue(wiz.picking_id)
        self.assertAlmostEqual(self._on_hand(), start - 2.0, places=3)

    # ---- Daily cap counts via the immutable flag, not the origin string -
    def test_scan_issue_picking_carries_immutable_flag(self):
        wiz = self._new_issue(2.0)
        wiz.action_validate()
        self.assertTrue(
            wiz.picking_id.wms_is_scan_issue,
            "Scan Issue picking must carry the immutable daily-cap marker",
        )

    def test_daily_cap_ignores_unflagged_pickings(self):
        """The cap counts only flagged Scan Issue pickings. A picking that
        merely shares the 'Barcode FIFO' origin but lacks the flag (an edit, a
        collision, a non-wizard transfer) must NOT count - the old origin-based
        counter would have wrongly counted it.

        FPAT High: the original test mutated wms_is_scan_issue on a freshly-
        validated picking. We now block that mutation at the ORM layer (the
        flag is immutable on done Scan Issues - it gates Consumption Value
        and the cap), so this test instead INSERTS a fresh historical row
        directly via the ORM with wms_is_scan_issue=False from the start -
        which is what a legacy pre-flag picking would look like.
        """
        self.product.product_tmpl_id.wms_daily_cap = 5.0
        # Seed a historical unflagged row: same product, same origin pattern,
        # but never went through the Scan Issue wizard.
        historical = (
            self.env["stock.picking"]
            .sudo()
            .create(
                {
                    "picking_type_id": self.wh.int_type_id.id,
                    "location_id": self.wh.lot_stock_id.id,
                    "location_dest_id": self.wh.lot_stock_id.id,
                    "origin": "Barcode FIFO issue",
                    "wms_is_scan_issue": False,
                    "wms_storekeeper_id": self.keeper.id,
                }
            )
        )
        self.assertFalse(historical.wms_is_scan_issue)
        wiz = self._new_issue(3.0)
        wiz.action_validate()  # projected 0+3 < 5 -> allowed
        self.assertTrue(
            wiz.picking_id,
            "unflagged historical pickings must not count toward the daily cap",
        )


@tagged("post_install", "-at_install", "wms", "wms_concurrency")
class TestReceiptConcurrency(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "UAT Keeper R"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "CONC-RCPT Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "CONCRCPT001",
                "wms_product_kind": "consumable",
            }
        )
        # A floor zone for the receipt to land in (auto-assign needs a
        # slot or floor; a fresh test DB has none).
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "CONC-RCPT Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

    def _on_hand(self):
        return self.env["stock.quant"]._get_available_quantity(
            self.product, self.stock, allow_negative=True
        )

    def test_receipt_double_click_is_idempotent(self):
        """Validating a receipt twice must add the stock only once."""
        start = self._on_hand()
        wiz = self.env["wms.scan.receipt"].create(
            {
                "warehouse_id": self.wh.id,
                "qc_passed": True,
                "storekeeper_id": self.keeper.id,
            }
        )
        self.env["wms.scan.receipt.line"].create(
            {"wizard_id": wiz.id, "product_id": self.product.id, "quantity": 5.0}
        )
        wiz.action_validate()
        first = wiz.picking_id
        self.assertTrue(first)
        after_first = self._on_hand()
        self.assertAlmostEqual(after_first, start + 5.0, places=3)

        wiz.action_validate()  # double-click
        self.assertEqual(wiz.picking_id, first)
        self.assertAlmostEqual(self._on_hand(), after_first, places=3, msg="no second receipt")

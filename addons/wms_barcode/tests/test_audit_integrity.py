# -*- coding: utf-8 -*-
"""Tests for the audit-trail invariant added in wms_barcode 19.0.1.7.0.

The invariant is enforced at TWO layers:

1. A PostgreSQL CHECK constraint on stock_picking (the DB-level guarantee
   that no SQL/XML-RPC/import path can bypass).
2. An @api.constrains for friendly error messages through the normal
   form-validate path.

These tests exercise layer 1 directly via raw SQL UPDATE. Layer 1 is
what we actually rely on for security; layer 2 is a UX enhancement and
is harder to test reliably because stock.picking's own button_validate
workflow runs many other checks before the field write reaches our
constraint.

Note on cursor handling: TransactionCase rolls back the whole test at
tearDown. We therefore (a) never call cr.commit() (it breaks the test
fixture isolation Odoo guards against), and (b) wrap constraint-
violating UPDATEs in self.env.cr.savepoint() so the aborted-transaction
state from the IntegrityError is rolled back to a clean savepoint
before tearDown runs.
"""
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


@tagged("post_install", "-at_install", "wms", "wms_audit")
class TestAuditTrailInvariant(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Picking = cls.env["stock.picking"]
        cls.picking_type = cls.env.ref("stock.picking_type_internal")
        cls.src = cls.env.ref("stock.stock_location_stock")
        cls.dst = cls.env["stock.location"].search([("usage", "=", "internal")], limit=1)

    def _make_picking(self, origin):
        return self.Picking.create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.src.id,
                "location_dest_id": self.dst.id,
                "origin": origin,
            }
        )

    def test_db_check_blocks_done_without_storekeeper(self):
        """Direct SQL UPDATE to state='done' on a WMS picking without a
        storekeeper anchor MUST raise IntegrityError. This is the
        security guarantee — nothing can bypass it."""
        pk = self._make_picking("Barcode FIFO-TEST-001")
        with mute_logger("odoo.sql_db"):
            with self.assertRaises(IntegrityError):
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        "UPDATE stock_picking SET state=%s WHERE id=%s",
                        ("done", pk.id),
                    )

    def test_db_check_allows_non_barcode_origin(self):
        """Non-WMS pickings (PO-..., MO-..., manual entry) are not
        subject to the audit triplet — the CHECK condition short-circuits
        on 'origin NOT LIKE Barcode%' before checking the storekeeper."""
        pk = self._make_picking("PO-12345")
        # No exception expected; the UPDATE must succeed.
        self.env.cr.execute(
            "UPDATE stock_picking SET state=%s WHERE id=%s",
            ("done", pk.id),
        )
        # Verify within the same transaction (no commit — TransactionCase
        # rolls back at tearDown, which is exactly what we want for test
        # isolation).
        self.env.cr.execute("SELECT state FROM stock_picking WHERE id=%s", (pk.id,))
        self.assertEqual(self.env.cr.fetchone()[0], "done")

    def test_db_check_allows_legacy_flag(self):
        """Rows flagged wms_audit_legacy=TRUE are grandfathered — the
        CHECK accepts them even without a storekeeper. This is how the
        pre-migration preserves historical data.

        Note: we set state AND wms_audit_legacy in ONE SQL UPDATE rather
        than writing legacy via the ORM first. ORM writes go to a cache
        that is not flushed before raw cr.execute(), so a two-step
        approach would see the legacy column still FALSE when the
        UPDATE's CHECK fires.
        """
        pk = self._make_picking("Barcode FIFO-LEGACY-003")
        self.env.cr.execute(
            "UPDATE stock_picking SET state=%s, wms_audit_legacy=TRUE WHERE id=%s",
            ("done", pk.id),
        )
        self.env.cr.execute(
            "SELECT state, wms_audit_legacy FROM stock_picking WHERE id=%s",
            (pk.id,),
        )
        row = self.env.cr.fetchone()
        self.assertEqual(row[0], "done")
        self.assertTrue(row[1])

    def test_db_check_allows_done_with_storekeeper(self):
        """The happy path: a WMS picking WITH a storekeeper anchor can
        legitimately be marked done. Set state AND storekeeper in one
        SQL UPDATE to avoid the ORM-cache-flush gap."""
        keeper = self.env["wms.storekeeper"].search([], limit=1)
        if not keeper:
            keeper = self.env["wms.storekeeper"].create({"name": "WMS-TEST-KEEPER"})
        # Make sure the keeper row is in the DB before our raw SQL.
        self.env.flush_all()
        pk = self._make_picking("Barcode FIFO-TEST-004")
        self.env.cr.execute(
            "UPDATE stock_picking SET state=%s, wms_storekeeper_id=%s WHERE id=%s",
            ("done", keeper.id, pk.id),
        )
        self.env.cr.execute("SELECT state FROM stock_picking WHERE id=%s", (pk.id,))
        self.assertEqual(self.env.cr.fetchone()[0], "done")

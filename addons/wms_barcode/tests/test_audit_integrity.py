# -*- coding: utf-8 -*-
"""Tests for the audit-trail invariant added in wms_barcode 19.0.1.7.0.

Verifies the DB-level CHECK constraint and the @api.constrains both fire
on the same conditions. Without these, a manager-side form save or any
XML-RPC client could silently mark a Barcode-originated picking 'done'
with no storekeeper anchor.
"""
from odoo.exceptions import ValidationError
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

    def test_done_without_storekeeper_blocks_via_constrains(self):
        """ORM write to state='done' fires @api.constrains."""
        pk = self._make_picking("Barcode FIFO-TEST-001")
        with self.assertRaises(ValidationError):
            pk.state = "done"

    def test_done_without_storekeeper_blocks_via_sql_check(self):
        """Direct SQL bypass still trips the DB CHECK."""
        pk = self._make_picking("Barcode FIFO-TEST-002")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env.cr.execute(
                "UPDATE stock_picking SET state=%s WHERE id=%s",
                ("done", pk.id),
            )

    def test_non_barcode_origin_is_unrestricted(self):
        """Standard non-WMS pickings are unaffected."""
        pk = self._make_picking("PO-12345")
        pk.state = "done"
        self.assertEqual(pk.state, "done")

    def test_legacy_flag_grandfathers_row(self):
        """A row flagged wms_audit_legacy passes the CHECK."""
        pk = self._make_picking("Barcode FIFO-LEGACY-003")
        pk.wms_audit_legacy = True
        pk.state = "done"
        self.assertEqual(pk.state, "done")
        self.assertTrue(pk.wms_audit_legacy)

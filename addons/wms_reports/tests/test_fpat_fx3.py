"""FPAT FX-3 regressions: security + DR hardening.

  * Stored XSS in the low-stock cron's manager Discuss inbox: product names
    must be HTML-escaped.
  * wms_is_scan_issue clear via ORM is rejected on done WMS pickings (the
    write() override gives operators a friendly error). The flag gates the
    daily-cap counter and the Consumption Value report; flipping it would
    silently rewrite history.
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx3")
class TestFpatFx3StoredXss(TransactionCase):
    def test_low_stock_cron_escapes_product_name(self):
        # Grant the admin the WMS Manager group so the notify helper
        # finds a recipient.
        manager = self.env.ref("wms_location.group_wms_manager")
        admin = self.env.ref("base.user_admin")
        admin.write({"group_ids": [(4, manager.id)]})
        product = self.env["product.product"].create(
            {
                "name": "<img src=x onerror=alert(1)>",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        self.env["wms.forecast"].create({"product_id": product.id, "reorder_qty": 5.0})
        self.env.flush_all()
        self.env["wms.stock.alert"]._cron_check_low_stock()
        msg = self.env["mail.message"].search(
            [("subject", "like", "%need reordering%")], order="id desc", limit=1
        )
        self.assertTrue(msg, "low-stock alert should have been posted")
        body = msg.body or ""
        # The dangerous tag must be ESCAPED, not present as live HTML.
        self.assertIn("&lt;img", body, "product name must be HTML-escaped")
        self.assertNotIn("<img src=x", body, "raw injection tag must not appear")


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx3")
class TestFpatFx3ScanIssueImmutable(TransactionCase):
    def test_orm_write_clearing_flag_on_done_raises(self):
        """The ORM write override gives operators a friendly error when
        they try to clear the wms_is_scan_issue marker on a done WMS-
        originated picking. The DB CHECK is the SQL backstop (separate test
        with savepoint + raw SQL)."""
        wh = self.env["stock.warehouse"].search([], limit=1)
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "FX3 Keeper"})
        product = self.env["product.product"].create(
            {
                "name": "FX3 Imm Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        # Set the test barcode BEFORE stock lands: post-P2, stock movement
        # freezes a product's SKU/barcode (they are then in circulation), so a
        # barcode rename must happen pre-stock. This is the intended freeze
        # behaviour, not a test workaround.
        product.barcode = "FX3IMMUTABLE1"
        self.env["stock.quant"]._update_available_quantity(product, wh.lot_stock_id, 10.0)
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": wh.id,
                "requested_qty": 2.0,
                "last_scan": "FX3IMMUTABLE1",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "FX3 immutability test",
                "storekeeper_id": keeper.id,
                "issued_for": "other",
            }
        )
        wiz.last_scan = "FX3IMMUTABLE1"
        wiz.action_plan()
        wiz.action_validate()
        picking = wiz.picking_id
        self.assertTrue(picking)
        self.assertTrue(picking.wms_is_scan_issue)
        self.assertEqual(picking.state, "done")
        with self.assertRaises(ValidationError):
            picking.write({"wms_is_scan_issue": False})

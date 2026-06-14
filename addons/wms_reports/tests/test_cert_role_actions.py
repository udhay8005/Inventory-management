"""UI certification — role-specific action coverage.

Covers the Buyer's central daily action (forecast -> draft PO) and a bound
server-action privilege boundary that the menu-smoke (act_window only) can't
reach.
"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ._cert_roles import CertRolesMixin


@tagged("post_install", "-at_install", "wms", "wms_ui_cert", "wms_cert_actions")
class TestCertRoleActions(CertRolesMixin, TransactionCase):
    def test_buyer_push_to_po_creates_draft_order(self):
        vendor = self.env["res.partner"].create({"name": "CERT Vendor", "supplier_rank": 1})
        product = self.env["product.product"].create(
            {
                "name": "CERT Buy Item",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
                "seller_ids": [(0, 0, {"partner_id": vendor.id, "price": 5.0})],
            }
        )
        fc = self.env["wms.forecast"].create({"product_id": product.id, "reorder_qty": 12.0})

        # Buyer runs the "push reorder suggestion to a draft PO" action. This
        # also certifies the group_buyer -> purchase.group_purchase_user implied
        # wiring actually permits creating a purchase.order.
        action = fc.with_user(self.role("BUYER")).action_push_to_po()
        self.assertEqual(action.get("res_model"), "purchase.order")
        po = self.env["purchase.order"].search([("partner_id", "=", vendor.id)], limit=1)
        self.assertTrue(po, "a draft PO must be created")
        self.assertEqual(po.state, "draft")
        self.assertTrue(
            any(line.product_id == product and line.product_qty == 12.0 for line in po.order_line),
            "the PO line must carry the product and the reorder qty",
        )

    def test_buyer_push_to_po_without_vendor_warns_not_crashes(self):
        product = self.env["product.product"].create(
            {
                "name": "CERT NoVendor Item",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        fc = self.env["wms.forecast"].create({"product_id": product.id, "reorder_qty": 3.0})
        action = fc.with_user(self.role("BUYER")).action_push_to_po()
        self.assertEqual(
            (action or {}).get("tag"),
            "display_notification",
            "no-vendor must warn gracefully, not create a PO or crash",
        )

    def test_baseline_keeper_cannot_bulk_generate_barcodes(self):
        """The barcode back-fill server action (Action menu on the product list)
        mutates product barcodes; a baseline keeper (catalog read-only) must be
        refused at the product-write ACL, not silently allowed."""
        product = self.env["product.product"].create(
            {
                "name": "CERT NeedsBarcode",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        with self.assertRaises(AccessError):
            product.product_tmpl_id.with_user(
                self.role("KEEPER_BASE")
            ).action_generate_missing_barcodes()

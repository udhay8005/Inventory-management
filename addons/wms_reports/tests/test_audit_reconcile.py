"""High - audit acceptance must reconcile (apply the count-time DELTA to the
live quantity), not blindly overwrite live stock with the stale count - which
would erase issues/receipts that happened during the audit window."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_audit_reconcile")
class TestAuditAcceptReconcile(TransactionCase):
    def test_accept_applies_delta_not_overwrite(self):
        product = self.env["product.product"].create(
            {"name": "Audit Reconcile", "is_storable": True}
        )
        slot = self.env.ref("stock.stock_location_stock")
        # Live book has risen to 12 (e.g. a receipt during the audit window).
        self.env["stock.quant"]._update_available_quantity(product, slot, 12.0)

        audit = self.env["wms.audit"].create({"state": "submitted"})
        self.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": slot.id,
                "product_id": product.id,
                "expected_qty": 10.0,  # book at count time
                "counted_qty": 8.0,  # physically found -> -2 discrepancy
            }
        )
        audit.action_review_accept()

        quant = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", slot.id)]
        )
        # Reconcile: 12 (current) + (8 - 10) = 10. A blind overwrite would have
        # wiped the receipt and left 8.
        self.assertEqual(sum(quant.mapped("quantity")), 10.0)

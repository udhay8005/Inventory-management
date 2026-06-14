"""High - audit acceptance must reconcile (apply the count-time DELTA to the
live quantity), not blindly overwrite live stock with the stale count - which
would erase issues/receipts that happened during the audit window."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_audit_reconcile")
class TestAuditAcceptReconcile(TransactionCase):
    def setUp(self):
        super().setUp()
        # Accept now requires a WMS Manager (in-method has_group re-check);
        # the default test user is the superuser, which is NOT in that group.
        self.mgr = self.env["res.users"].create(
            {
                "name": "Reconcile Mgr",
                "login": "reconcile_mgr",
                "group_ids": [(6, 0, [self.env.ref("wms_location.group_wms_manager").id])],
            }
        )

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
        audit.with_user(self.mgr).action_review_accept()

        quant = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", slot.id)]
        )
        # Reconcile: 12 (current) + (8 - 10) = 10. A blind overwrite would have
        # wiped the receipt and left 8.
        self.assertEqual(sum(quant.mapped("quantity")), 10.0)

    def test_accept_creates_delta_for_genuinely_new_stock(self):
        product = self.env["product.product"].create(
            {"name": "Audit New Stock", "is_storable": True}
        )
        slot = self.env.ref("stock.stock_location_stock")
        # No book, no live quant; the count found 5 physical units (delta = +5).
        audit = self.env["wms.audit"].create({"state": "submitted"})
        self.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": slot.id,
                "product_id": product.id,
                "expected_qty": 0.0,
                "counted_qty": 5.0,
            }
        )
        audit.with_user(self.mgr).action_review_accept()
        quant = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", slot.id)]
        )
        self.assertEqual(sum(quant.mapped("quantity")), 5.0)

    def test_accept_does_not_recreate_emptied_slot(self):
        product = self.env["product.product"].create({"name": "Audit Emptied", "is_storable": True})
        slot = self.env.ref("stock.stock_location_stock")
        # Book 10 at count, found 8 (delta -2), but an issue emptied the slot to
        # 0 during the window (no live quant). Accept must NOT re-create it at the
        # stale count of 8 (the old code did).
        audit = self.env["wms.audit"].create({"state": "submitted"})
        self.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": slot.id,
                "product_id": product.id,
                "expected_qty": 10.0,
                "counted_qty": 8.0,
            }
        )
        audit.with_user(self.mgr).action_review_accept()
        quant = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("location_id", "=", slot.id)]
        )
        self.assertEqual(sum(quant.mapped("quantity")), 0.0)

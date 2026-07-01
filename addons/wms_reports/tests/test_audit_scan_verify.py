"""Optional scan-to-verify on an audit line: while counting, the keeper can
scan the product barcode and the Scan column confirms it's the right item — a
cheap guard against counting a look-alike (similar feed sacks / medicine boxes).
Advisory only: it never blocks the count.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_audit_scan")
class TestAuditScanVerify(TransactionCase):
    def test_scan_status_blank_match_mismatch(self):
        slot = self.env.ref("stock.stock_location_stock")
        prod = self.env["product.product"].create(
            {"name": "Scan Audit Widget", "is_storable": True, "barcode": "AUDITSCAN1"}
        )
        audit = self.env["wms.audit"].create({"state": "draft"})
        line = self.env["wms.audit.line"].create(
            {"audit_id": audit.id, "location_id": slot.id, "product_id": prod.id}
        )

        # Not scanned yet.
        self.assertEqual(line.scan_status, "blank")

        # The line's own barcode confirms it.
        line.scan_confirm = "AUDITSCAN1"
        self.assertEqual(line.scan_status, "match")

        # A different / unknown code flags a wrong item.
        line.scan_confirm = "SOMEOTHERCODE"
        self.assertEqual(line.scan_status, "mismatch")

        # The SKU (default_code) is also a valid confirm.
        prod.default_code = "SKU-AUDIT-1"
        line.scan_confirm = "SKU-AUDIT-1"
        self.assertEqual(line.scan_status, "match")

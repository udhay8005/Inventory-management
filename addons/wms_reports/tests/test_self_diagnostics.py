"""Maturity: one-button self-diagnostics. Read-only health + integrity checks;
on a clean DB the integrity probes must report pass and the wizard renders a
result table with an overall verdict."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_diagnostics")
class TestSelfDiagnostics(TransactionCase):
    def test_checks_run_and_integrity_passes(self):
        wiz = self.env["wms.self.diagnostics"].create({})
        checks = wiz._run_checks()
        self.assertGreaterEqual(len(checks), 6)
        status = {c["check"]: c["status"] for c in checks}
        # Integrity invariants must hold on a clean DB.
        self.assertEqual(status["Duplicate SKUs"], "pass")
        self.assertEqual(status["Duplicate barcodes"], "pass")
        self.assertEqual(status["Negative on-hand"], "pass")
        # create() auto-populates; action_run re-runs and renders.
        self.assertTrue(wiz.result_html, "diagnostics should render a result table")
        self.assertIn(wiz.overall, ("pass", "warn", "fail"))
        wiz.action_run()
        self.assertTrue(wiz.result_html)

    def _negative_onhand_status(self):
        checks = self.env["wms.self.diagnostics"].create({})._run_checks()
        return {c["check"]: c["status"] for c in checks}["Negative on-hand"]

    def test_negative_onhand_ignores_virtual_locations(self):
        """A negative quant in a VIRTUAL location (Vendors/Customers) is normal
        double-entry — every receipt drives the supplier location negative — and
        must NOT trip the Negative on-hand check. A negative quant in an INTERNAL
        (usable) location is a real oversell and must."""
        product = self.env["product.product"].create(
            {"name": "Diag Negative Probe", "is_storable": True, "type": "consu"}
        )
        suppliers = self.env.ref("stock.stock_location_suppliers")  # usage=supplier
        internal = self.env.ref("stock.stock_location_stock")  # usage=internal

        # Negative in a virtual (supplier) location -> still pass.
        self.env["stock.quant"].sudo().create(
            {"product_id": product.id, "location_id": suppliers.id, "quantity": -3.0}
        )
        self.assertEqual(
            self._negative_onhand_status(),
            "pass",
            "a negative quant in a virtual location must be ignored",
        )

        # Negative in an internal (usable) location -> fail.
        self.env["stock.quant"].sudo().create(
            {"product_id": product.id, "location_id": internal.id, "quantity": -1.0}
        )
        self.assertEqual(
            self._negative_onhand_status(),
            "fail",
            "a negative quant in an internal location must be flagged",
        )

    def test_health_detail_has_no_noneh_when_no_backup(self):
        """With no backup recorded, last_backup age is None; the System-health
        detail must read 'never', never the bare 'Noneh'."""
        checks = self.env["wms.self.diagnostics"].create({})._run_checks()
        health = next(c for c in checks if c["check"].startswith("System health"))
        self.assertNotIn("Noneh", health["detail"])
        self.assertIn("last_backup=never", health["detail"])

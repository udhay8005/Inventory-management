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

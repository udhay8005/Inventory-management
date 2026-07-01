"""Spec guard: the shipped high-value approval threshold default is Rs 20,000.

The gaushala's rule is "issues over Rs 20,000 need approval." That number lives
in the seeded ir.config_parameter wms_barcode.high_value_threshold. This test
pins the shipped default so a future edit can't silently drift it back to the
old Rs 5,000 (the value the corrective migration 19.0.1.49.0 also realigns).
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestApprovalThresholdDefault(TransactionCase):
    def test_shipped_default_is_20000(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("wms_barcode.high_value_threshold")
        )
        self.assertEqual(
            value,
            "20000",
            "High-value approval threshold default must be Rs 20,000 per the "
            "gaushala spec (got %r)." % value,
        )

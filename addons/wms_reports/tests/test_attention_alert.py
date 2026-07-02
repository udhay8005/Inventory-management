"""Daily "needs attention" alert cron — proactive push of duplicate barcodes,
dead stock, and open repair orders that previously only surfaced when an admin
opened Self-Diagnostics.

The notify delivery itself is covered by the low-stock alert test (same
notify_wms_managers helper); here we prove the new detection code runs cleanly
both when everything is fine (silent) and when there IS something to flag.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_attention")
class TestAttentionAlert(TransactionCase):
    def test_attention_cron_is_silent_and_safe_when_clean(self):
        # Runs all three detectors (duplicate-barcode SQL, dead-stock count,
        # repair-pending count) — must never raise, even with nothing to flag.
        self.env["wms.stock.alert"]._cron_check_attention()

    def test_attention_cron_runs_with_dead_stock(self):
        product = self.env["product.product"].create(
            {
                "name": "ATT Dead Widget",
                "type": "consu",
                "wms_product_kind": "consumable",
            }
        )
        self.env["wms.forecast"].create(
            {
                "product_id": product.id,
                "daily_avg": 0.0,
                "monthly_avg": 0.0,
                "predicted_qty": 0.0,
                "velocity_class": "dead",
                "reorder_qty": 0.0,
                "on_hand": 0.0,
                "horizon_days": 30,
            }
        )
        # Dead stock is present -> the notify branch is exercised; must not raise.
        self.env["wms.stock.alert"]._cron_check_attention()

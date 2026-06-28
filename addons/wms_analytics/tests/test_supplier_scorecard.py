"""Wave 2 — Supplier scorecard + ledger SQL views.

Seeds two suppliers with contrasting quality histories and asserts the
aggregate counts, the acceptance / rejection rates, the weighted quality score,
and the per-lot ledger rows.
"""

from datetime import timedelta

from odoo import fields
from odoo.addons.wms_analytics.models.wms_supplier_scorecard import (
    PENALTY_PER_DAMAGE,
    PENALTY_PER_EXPIRY,
    PENALTY_PER_RECALL,
    PENALTY_PER_REJECTION,
)
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestSupplierScorecard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "SUP Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "SUP Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "SUPMED01",
            }
        )
        # Two suppliers: "good" delivers clean stock; "bad" accrues every penalty.
        cls.good = cls.env["res.partner"].create({"name": "SUP Good Supplier"})
        cls.bad = cls.env["res.partner"].create({"name": "SUP Bad Supplier"})
        # Recall activation and QC reject are manager-gated.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]

    @classmethod
    def _lot(cls, name, supplier, days, qty=10.0):
        lot = cls.env["stock.lot"].create(
            {
                "name": name,
                "product_id": cls.med.id,
                "company_id": cls.env.company.id,
                "wms_supplier_id": supplier.id,
                "wms_supplier_batch": "B-%s" % name,
                "expiration_date": fields.Datetime.now() + timedelta(days=days),
            }
        )
        if qty:
            cls.env["stock.quant"]._update_available_quantity(cls.med, cls.floor, qty, lot_id=lot)
        return lot

    def _score(self, partner):
        self.env.flush_all()
        return self.env["wms.supplier.scorecard"].search([("partner_id", "=", partner.id)])

    # ------------------------------------------------------------------ #

    def test_clean_supplier_is_perfect(self):
        # Two healthy lots, no quality events → 100 score, 100% acceptance.
        self._lot("SUP-G1", self.good, 200)
        self._lot("SUP-G2", self.good, 300)
        row = self._score(self.good)
        self.assertTrue(row, "a supplier with lots must appear on the scorecard")
        self.assertEqual(row.lots_received, 2)
        self.assertEqual(row.recall_count, 0)
        self.assertEqual(row.quarantine_reject_count, 0)
        self.assertEqual(row.expired_lot_count, 0)
        self.assertEqual(row.quality_score, 100.0)
        self.assertEqual(row.acceptance_rate, 100.0)
        self.assertEqual(row.rejection_rate, 0.0)
        self.assertEqual(row.quality_band, "good")

    def test_bad_supplier_accrues_every_penalty(self):
        # 4 lots: one expired, one recalled, one QC-rejected, one damaged.
        good_lot = self._lot("SUP-B-OK", self.bad, 200)
        self._lot("SUP-B-EXP", self.bad, -5)  # already expired (drives the expiry penalty)
        recalled_lot = self._lot("SUP-B-REC", self.bad, 100)
        rejected_lot = self._lot("SUP-B-REJ", self.bad, 100)

        # Recall the recalled_lot (named on a supplier-mode notice too).
        recall = self.env["wms.lot.recall"].create(
            {
                "mode": "supplier",
                "supplier_id": self.bad.id,
                "reason": "supplier contamination notice",
                "lot_ids": [(6, 0, recalled_lot.ids)],
            }
        )
        recall.action_recall()

        # QC hold on rejected_lot, then reject it.
        qc = self.env["wms.lot.quarantine"].create(
            {
                "reason": "off-spec on intake",
                "lot_ids": [(6, 0, rejected_lot.ids)],
            }
        )
        qc.action_reject()

        # Confirmed damage attributed to the bad supplier. We bypass the heavy
        # picking machinery by stamping the confirmed snapshot via sudo (the
        # scorecard only reads state/qty/value/supplier off the row).
        dmg = self.env["wms.damage"].create(
            {
                "product_id": self.med.id,
                "quantity": 3.0,
                "source_slot_id": self.floor.id,
                "reason": "broken",
                "wms_supplier_id": self.bad.id,
            }
        )
        dmg.sudo().write(
            {"state": "confirmed", "damage_value": 30.0, "wms_supplier_id": self.bad.id}
        )

        row = self._score(self.bad)
        self.assertEqual(row.lots_received, 4)
        self.assertEqual(row.recall_count, 1, "one recall attributed to the supplier")
        self.assertEqual(row.quarantine_total, 1)
        self.assertEqual(row.quarantine_reject_count, 1)
        self.assertEqual(row.expired_lot_count, 1)
        self.assertEqual(row.damaged_qty, 3.0)
        self.assertEqual(row.damaged_value, 30.0)

        # quality_score = 100 - recall - rejection - (damage flag) - expiry.
        expected = float(
            100
            - PENALTY_PER_RECALL
            - PENALTY_PER_REJECTION
            - PENALTY_PER_DAMAGE
            - PENALTY_PER_EXPIRY
        )
        self.assertEqual(row.quality_score, expected)

        # 3 of 4 lots are "bad" (recalled + rejected + expired); the OK lot is
        # the only accepted one → 25% acceptance, 75% rejection.
        self.assertEqual(row.rejection_rate, 75.0)
        self.assertEqual(row.acceptance_rate, 25.0)

        # Reference good_lot so it counts toward lots_received but stays clean.
        self.assertEqual(good_lot.wms_lot_state, "available")

    def test_ledger_lists_each_received_lot(self):
        lot_a = self._lot("SUP-L1", self.good, 150, qty=7.0)
        lot_b = self._lot("SUP-L2", self.good, 150, qty=0.0)  # received, none on hand
        self.env.flush_all()
        Ledger = self.env["wms.supplier.ledger"]
        rows = Ledger.search([("partner_id", "=", self.good.id)])
        self.assertGreaterEqual(len(rows), 2)
        by_lot = {r.lot_id.id: r for r in rows}
        self.assertIn(lot_a.id, by_lot)
        self.assertIn(lot_b.id, by_lot)
        self.assertEqual(by_lot[lot_a.id].on_hand, 7.0)
        self.assertEqual(by_lot[lot_b.id].on_hand, 0.0)
        self.assertEqual(by_lot[lot_a.id].supplier_batch, "B-SUP-L1")
        self.assertEqual(by_lot[lot_a.id].lot_state, "available")

"""V20-021 — warehouse simulation: an end-to-end run of the whole Wave-1
perishable engine (receive multiple batches -> FEFO -> recall -> quarantine ->
expiry report), asserting correctness and stock conservation throughout, plus a
scaled FEFO ordering check."""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestWarehouseSimulation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "SIM Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "SIM Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "SIM Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "SIMMED01",
            }
        )
        cls.env.user.write({"group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)]})

    def _receive(self, batch, days, qty=10):
        wiz = self.env["wms.scan.receipt"].create(
            {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
        )
        self.env["wms.scan.receipt.line"].create(
            {
                "wizard_id": wiz.id,
                "product_id": self.med.id,
                "quantity": qty,
                "location_dest_id": self.floor.id,
                "wms_batch": batch,
                "wms_expiry": fields.Date.today() + timedelta(days=days),
            }
        )
        # The sim exercises FEFO / recall / quarantine, not the V20-018 receiving
        # guard (tested separately); accept short-dated batches as a manager would.
        wiz.with_context(wms_allow_short_dated=True).action_validate()
        return self.env["stock.lot"].search(
            [("product_id", "=", self.med.id), ("name", "=", batch)], limit=1
        )

    def _plan_lots(self, qty):
        plan, _missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.med.id, qty, parent_location_id=self.stock.id
        )
        return [q.lot_id for q, _take in plan]

    def _on_hand_total(self):
        return sum(
            self.env["stock.quant"]
            .search([("product_id", "=", self.med.id), ("location_id", "=", self.floor.id)])
            .mapped("quantity")
        )

    def test_full_perishable_lifecycle(self):
        # Receive three batches with different shelf life (all >= 60d so the
        # near-expiry receiving guard passes).
        b_mid = self._receive("SIM-MID", 90)
        b_near = self._receive("SIM-NEAR", 65)  # earliest expiry
        b_far = self._receive("SIM-FAR", 200)
        self.assertEqual(self._on_hand_total(), 30.0, "30 units across three batches")

        # FEFO: the earliest-expiring batch is planned first.
        self.assertEqual(self._plan_lots(5)[0], b_near, "FEFO picks the soonest-expiring batch")

        # Recall the mid batch: excluded from issue, no longer planned.
        self.env["wms.lot.recall"].create(
            {"mode": "manual", "reason": "supplier notice", "lot_ids": [(6, 0, b_mid.ids)]}
        ).action_recall()
        self.assertNotIn(b_mid, self._plan_lots(30), "a recalled batch is not issuable")

        # Quarantine the far batch: only the near batch remains issuable.
        self.env["wms.lot.quarantine"].create({"reason": "QC hold", "lot_ids": [(6, 0, b_far.ids)]})
        issuable = set(self._plan_lots(30))
        self.assertEqual(issuable, {b_near}, "only the available batch is issuable")

        # Stock is conserved — recall/quarantine freeze, they do not destroy.
        self.assertEqual(self._on_hand_total(), 30.0, "freezing does not change on-hand")

        # The per-lot expiry report sees all three batches. Flush first: the SQL
        # view reads the stored wms_effective_expiry column directly, so pending
        # ORM computes must be written out before the raw read.
        self.env.flush_all()
        report = self.env["wms.lot.expiry.alert"].search([("product_id", "=", self.med.id)])
        self.assertEqual(len(report), 3, "every batch shows on the per-lot expiry report")

    def test_scaled_fefo_orders_many_lots(self):
        # Receive 12 batches in shuffled expiry order; FEFO must return them
        # strictly earliest-expiry-first regardless of arrival order.
        order = [220, 40, 130, 10, 300, 70, 25, 180, 55, 95, 5, 160]
        for i, days in enumerate(order):
            self._receive("SC-%02d" % i, days, qty=2)
        lots = self._plan_lots(24)  # all 24 units across 12 lots
        expiries = [lot.expiration_date for lot in lots]
        self.assertEqual(
            expiries, sorted(expiries), "FEFO returns lots in non-decreasing expiry order"
        )

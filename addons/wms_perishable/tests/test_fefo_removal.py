"""V20-009 — FEFO removal ordering reads the per-quant wms_effective_expiry:
earliest-expiry-first for perishables, FIFO unchanged for non-perishables, and
a move auto-splits across lots in FEFO order."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestFefoRemoval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.customers = cls.env.ref("stock.stock_location_customers")
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "FE Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "FE Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "FEMED01",
            }
        )

    def _lot(self, product, name, expiry):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": product.id,
                "company_id": self.env.company.id,
                "expiration_date": expiry,
            }
        )

    def _seed(self, product, lot, qty, in_date):
        self.env["stock.quant"]._update_available_quantity(product, self.floor, qty, lot_id=lot)
        q = self.env["stock.quant"].search(
            [
                ("product_id", "=", product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.floor.id),
            ],
            limit=1,
        )
        q.in_date = in_date
        return q

    def test_fefo_picks_earliest_expiry_over_fifo(self):
        # The later-expiry lot ARRIVES FIRST (older in_date) so plain FIFO would
        # pick it; FEFO must override and pick the earlier-expiring lot first.
        lot_late = self._lot(self.med, "FE-LATE", "2027-09-30 00:00:00")
        lot_early = self._lot(self.med, "FE-EARLY", "2027-03-31 00:00:00")
        q_late = self._seed(self.med, lot_late, 5.0, "2026-01-01 00:00:00")
        q_early = self._seed(self.med, lot_early, 5.0, "2026-03-01 00:00:00")
        ordered = (q_late | q_early)._wms_sorted_for_removal()
        self.assertEqual(ordered[0].lot_id, lot_early, "FEFO must pick the earliest-expiring lot")
        self.assertEqual(ordered[1].lot_id, lot_late)

    def test_non_perishable_lot_stays_fifo(self):
        # A lot-tracked NON-perishable (edge) must stay strict FIFO and ignore
        # the lots' expiry entirely — guards the kind gate against regression.
        tool = self.env["product.product"].create(
            {"name": "FE Tool", "type": "consu", "is_storable": True, "wms_product_kind": "tool"}
        )
        tool.tracking = "lot"
        lot_early = self._lot(tool, "FT-EARLY", "2027-03-31 00:00:00")
        lot_late = self._lot(tool, "FT-LATE", "2027-09-30 00:00:00")
        # Earlier-expiry lot arrives LATER; FIFO must still pick the older arrival.
        q_early = self._seed(tool, lot_early, 5.0, "2026-03-01 00:00:00")
        q_late = self._seed(tool, lot_late, 5.0, "2026-01-01 00:00:00")
        ordered = (q_early | q_late)._wms_sorted_for_removal()
        self.assertEqual(
            ordered[0].lot_id,
            lot_late,
            "non-perishable stays FIFO (oldest arrival), ignores expiry",
        )

    def test_issue_auto_splits_across_lots_in_fefo_order(self):
        lot_early = self._lot(self.med, "AS-EARLY", "2027-03-31 00:00:00")
        lot_late = self._lot(self.med, "AS-LATE", "2027-12-31 00:00:00")
        self._seed(self.med, lot_early, 20.0, "2026-02-01 00:00:00")
        self._seed(self.med, lot_late, 30.0, "2026-01-01 00:00:00")
        pick = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh.out_type_id.id,
                "location_id": self.floor.id,
                "location_dest_id": self.customers.id,
            }
        )
        self.env["stock.move"].create(
            {
                "description_picking": "AS issue",
                "product_id": self.med.id,
                "product_uom": self.med.uom_id.id,
                "product_uom_qty": 40.0,
                "picking_id": pick.id,
                "location_id": self.floor.id,
                "location_dest_id": self.customers.id,
            }
        )
        pick.action_confirm()
        pick.action_assign()
        self.assertEqual(pick.move_ids.state, "assigned", "40 of 50 on hand must fully reserve")
        by_lot = {ml.lot_id: ml.quantity for ml in pick.move_ids.move_line_ids}
        # FEFO: drain the earliest-expiring lot fully (20), then 20 from the later lot.
        self.assertEqual(by_lot.get(lot_early), 20.0, "all 20 from the earliest-expiry lot first")
        self.assertEqual(by_lot.get(lot_late), 20.0, "remaining 20 from the later lot")

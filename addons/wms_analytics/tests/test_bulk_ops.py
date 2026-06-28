"""Wave 2 #13 — Bulk Operations on lots.

Selecting N lots and running a bulk action creates ONE recall / quarantine
spanning all N, and transitions every lot. Run as a manager (the bulk methods
and the underlying recall/quarantine actions are manager-gated).
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestBulkOps(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # group_ids (Odoo 19), not groups_id. Bulk ops are manager-gated.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]

        cls.med = cls.env["product.product"].create(
            {
                "name": "BULK Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "tracking": "lot",
                "barcode": "BULKMED01",
            }
        )

    def _lots(self, n):
        return self.env["stock.lot"].create(
            [
                {
                    "name": "BULK-LOT-%02d" % i,
                    "product_id": self.med.id,
                    "company_id": self.env.company.id,
                }
                for i in range(n)
            ]
        )

    def test_bulk_recall_covers_all(self):
        lots = self._lots(4)
        before = self.env["wms.lot.recall"].search([])
        lots.with_context(active_ids=lots.ids).action_wms_bulk_recall()
        new = self.env["wms.lot.recall"].search([]) - before
        self.assertEqual(len(new), 1, "Exactly one recall should be created.")
        self.assertEqual(set(new.lot_ids.ids), set(lots.ids), "Recall must cover all lots.")
        self.assertEqual(new.state, "active")
        for lot in lots:
            self.assertEqual(lot.wms_lot_state, "recalled")

    def test_bulk_quarantine_covers_all(self):
        lots = self._lots(3)
        before = self.env["wms.lot.quarantine"].search([])
        lots.with_context(active_ids=lots.ids).action_wms_bulk_quarantine()
        new = self.env["wms.lot.quarantine"].search([]) - before
        self.assertEqual(len(new), 1, "Exactly one quarantine should be created.")
        self.assertEqual(set(new.lot_ids.ids), set(lots.ids))
        self.assertEqual(new.state, "held")
        for lot in lots:
            self.assertEqual(lot.wms_lot_state, "quarantine")

    def test_bulk_destroy_covers_all(self):
        lots = self._lots(2)
        before = self.env["wms.lot.quarantine"].search([])
        lots.with_context(active_ids=lots.ids).action_wms_bulk_destroy()
        new = self.env["wms.lot.quarantine"].search([]) - before
        self.assertEqual(len(new), 1)
        self.assertEqual(new.state, "destroyed")
        for lot in lots:
            self.assertEqual(lot.wms_lot_state, "destroyed")

    def test_empty_selection_raises(self):
        with self.assertRaises(UserError):
            self.env["stock.lot"].with_context(active_ids=[]).action_wms_bulk_recall()

    def test_non_manager_blocked(self):
        # Drop manager rights → bulk op must refuse.
        self.env.user.group_ids = [(3, self.env.ref("wms_location.group_wms_manager").id)]
        lots = self._lots(1)
        with self.assertRaises(UserError):
            lots.with_context(active_ids=lots.ids).action_wms_bulk_recall()

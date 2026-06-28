"""V20-014 — quarantine holds a lot (un-issuable) and cancels its reservations;
QC then releases it back to available, or rejects + destroys it. Manager-gated."""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestQuarantine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "QC Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "QC Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "QCMED01",
            }
        )
        cls.env.user.write({"group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)]})
        cls.clerk = cls.env["res.users"].create(
            {
                "name": "QC Clerk",
                "login": "qc_clerk",
                "group_ids": [(4, cls.env.ref("wms_location.group_wms_can_scan_issue").id)],
            }
        )

    def _lot(self, name):
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        return lot

    def _quarantine(self, lot):
        return self.env["wms.lot.quarantine"].create(
            {"reason": "QC hold", "lot_ids": [(6, 0, lot.ids)]}
        )

    def _plan(self, qty):
        return self.env["stock.location"].find_oldest_quants_for_product(
            self.med.id, qty, parent_location_id=self.stock.id
        )

    def test_hold_freezes_and_excludes(self):
        lot = self._lot("QC-A")
        q = self._quarantine(lot)
        self.assertEqual(lot.wms_lot_state, "quarantine")
        self.assertEqual(q.state, "held")
        plan, missing = self._plan(3)
        self.assertEqual(plan, [], "a quarantined lot must be excluded from issue")
        self.assertEqual(missing, 3)

    def test_release_restores_issuable(self):
        lot = self._lot("QC-REL")
        q = self._quarantine(lot)
        q.action_release()
        self.assertEqual(lot.wms_lot_state, "available")
        self.assertEqual(q.state, "released")
        plan, missing = self._plan(3)
        self.assertTrue(plan, "released lot is issuable again")
        self.assertEqual(missing, 0)

    def test_reject_then_destroy(self):
        lot = self._lot("QC-REJ")
        q = self._quarantine(lot)
        q.action_reject()
        self.assertEqual(q.state, "rejected")
        q.action_destroy()
        self.assertEqual(lot.wms_lot_state, "destroyed")
        self.assertEqual(q.state, "destroyed")
        self.assertEqual(self._plan(3)[0], [], "destroyed stock is not issuable")

    def test_non_manager_cannot_quarantine(self):
        lot = self._lot("QC-NM")
        # A non-manager has no create access on the model (ACL), so the create
        # is refused before the in-method manager check even runs.
        with self.assertRaises(AccessError):
            self.env["wms.lot.quarantine"].with_user(self.clerk).create(
                {"reason": "x", "lot_ids": [(6, 0, lot.ids)]}
            )

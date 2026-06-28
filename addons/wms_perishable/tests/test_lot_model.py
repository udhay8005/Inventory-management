"""V20-007 — stock.lot perishable lifecycle + supplier/expiry metadata."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLotModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "Lot Model Med",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "wms_product_kind": "medicine",
            }
        )

    def _lot(self, name="LM-001", **kw):
        vals = {"name": name, "product_id": self.product.id, "company_id": self.env.company.id}
        vals.update(kw)
        return self.env["stock.lot"].create(vals)

    def test_new_lot_defaults_available(self):
        self.assertEqual(self._lot().wms_lot_state, "available")

    def test_supplier_and_manufacture_metadata(self):
        partner = self.env["res.partner"].create({"name": "Cert Vet Supplier"})
        lot = self._lot(
            name="LM-SUP",
            wms_supplier_id=partner.id,
            wms_supplier_batch="SUP-A101",
            wms_supplier_invoice="INV-77",
            wms_manufacture_date="2026-01-15",
        )
        self.assertEqual(lot.wms_supplier_id, partner)
        self.assertEqual(lot.wms_supplier_batch, "SUP-A101")
        self.assertEqual(lot.wms_supplier_invoice, "INV-77")
        self.assertEqual(str(lot.wms_manufacture_date), "2026-01-15")

    def test_is_expired_compute(self):
        self.assertTrue(
            self._lot(name="LM-PAST", expiration_date="2020-01-01 00:00:00").wms_is_expired
        )
        self.assertFalse(
            self._lot(name="LM-FUT", expiration_date="2099-01-01 00:00:00").wms_is_expired
        )
        self.assertFalse(self._lot(name="LM-NONE").wms_is_expired)

    def test_lifecycle_state_transitions(self):
        lot = self._lot(name="LM-ST")
        for st in ("quarantine", "recalled", "destroyed", "available"):
            lot.wms_lot_state = st
            self.assertEqual(lot.wms_lot_state, st)

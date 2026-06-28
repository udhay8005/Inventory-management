"""V20-008 — stock.quant.wms_effective_expiry: lot expiry, else template fallback,
and it recomputes when the lot's expiry changes after the quant exists."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestEffectiveExpiry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.med = cls.env["product.product"].create(
            {
                "name": "EE Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "EEMED01",
            }
        )

    def _lot(self, name, expiry=None):
        vals = {
            "name": name,
            "product_id": self.med.id,
            "company_id": self.env.company.id,
        }
        if expiry:
            vals["expiration_date"] = expiry
        return self.env["stock.lot"].create(vals)

    def _quant(self, product, lot=None):
        return self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.stock.id,
                "quantity": 1.0,
                "lot_id": lot.id if lot else False,
            }
        )

    def test_lot_expiry_drives_effective(self):
        lot = self._lot("EE-A", "2027-03-15 08:00:00")
        q = self._quant(self.med, lot)
        self.assertEqual(str(q.wms_effective_expiry), "2027-03-15")

    def test_template_fallback_when_no_lot(self):
        # The fallback path is the no-lot case: a product carrying a template
        # wms_expiry_date but not lot-tracked (legacy / pre-migration stock).
        # (For a lot-tracked use_expiration_date product, product_expiry always
        # auto-fills lot.expiration_date, so the lot value wins there.)
        prod = self.env["product.product"].create(
            {"name": "EE Legacy", "type": "consu", "is_storable": True, "wms_product_kind": "tool"}
        )
        prod.product_tmpl_id.wms_expiry_date = "2026-09-30"
        q = self._quant(prod)  # tool is not lot-tracked -> no lot
        self.assertEqual(str(q.wms_effective_expiry), "2026-09-30")

    def test_recomputes_when_lot_expiry_changes(self):
        lot = self._lot("EE-C", "2027-01-01 00:00:00")
        q = self._quant(self.med, lot)
        self.assertEqual(str(q.wms_effective_expiry), "2027-01-01")
        lot.expiration_date = "2026-05-05 00:00:00"
        self.assertEqual(
            str(q.wms_effective_expiry), "2026-05-05", "stored field must recompute on lot change"
        )

    def test_non_perishable_without_expiry_is_empty(self):
        tool = self.env["product.product"].create(
            {"name": "EE Drill", "type": "consu", "is_storable": True, "wms_product_kind": "tool"}
        )
        q = self._quant(tool)  # not lot-tracked, no template expiry
        self.assertFalse(q.wms_effective_expiry)

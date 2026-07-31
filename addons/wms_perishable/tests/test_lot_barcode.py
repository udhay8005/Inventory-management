"""V20-016 — a lot has a printable label (product / batch / expiry / supplier,
barcode = lot name) that scans straight back to the lot."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLotBarcode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.med = cls.env["product.product"].create(
            {
                "name": "LB Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "LBMED01",
            }
        )
        cls.supplier = cls.env["res.partner"].create({"name": "Acme Pharma"})

    def _lot(self, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
                "wms_supplier_id": self.supplier.id,
            }
        )

    def test_lot_label_content(self):
        lot = self._lot("A101")
        vals = lot._wms_lot_label_vals()
        self.assertEqual(vals["barcode"], "A101", "barcode is the lot name (scans back to the lot)")
        self.assertEqual(vals["title"], lot.product_id.display_name)
        self.assertIn("A101", vals["subtitle"], "batch on the sub-line")
        self.assertIn("2027", vals["subtitle"], "expiry on the sub-line")
        self.assertIn("Acme Pharma", vals["subtitle"], "supplier on the sub-line")

    def test_label_renders_scannable_tspl(self):
        lot = self._lot("B202")
        printer = self.env["wms.label.printer"].create(
            {"name": "LB Printer", "system_name": "LB-TEST"}
        )
        tspl = printer.with_context(wms_print_dry_run=True).print_labels(
            [lot._wms_lot_label_vals()]
        )
        self.assertTrue(tspl, "the label renders to a TSPL job")
        self.assertIn(b"B202", tspl, "the lot barcode is encoded in the printed label")

    def test_print_action_returns_notification(self):
        lot = self._lot("C303")
        self.env["wms.label.printer"].create(
            {"name": "LB Default", "system_name": "LB-TEST", "is_default": True}
        )
        res = lot.with_context(wms_print_dry_run=True).action_wms_print_lot_label()
        self.assertEqual(res.get("type"), "ir.actions.client", "the button returns a notification")

    def test_scan_resolves_to_lot(self):
        lot = self._lot("D404")
        info = self.env["wms.barcode.alias"].resolve("D404")
        self.assertEqual(info.get("kind"), "lot", "scanning the lot label resolves to the lot")
        self.assertEqual(info.get("lot"), lot)
        self.assertEqual(info.get("product"), self.med)

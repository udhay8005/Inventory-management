"""UI certification — Product Onboard -> label print (daily flow + print).

Drives the Onboard wizard end to end: it must create the catalog product with
an auto-assigned barcode, place the opening stock in the slot, and return the
thermal-label report action — which must then render a real PDF.
"""

from odoo.tests import TransactionCase, tagged

from ._cert_roles import CertRolesMixin


@tagged("post_install", "-at_install", "wms", "wms_ui_cert", "wms_cert_onboard")
class TestCertOnboardPrint(CertRolesMixin, TransactionCase):
    def test_onboard_creates_stocked_product_and_prints_label(self):
        wiz = self.env["wms.product.onboard"].create(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "CERT Onboard Tool",
                            "wms_product_kind": "tool",
                            "initial_qty": 2.0,
                            "location_id": self.cert_location.id,
                        },
                    )
                ],
            }
        )
        action = wiz.action_onboard()

        # Onboard returns the thermal-label report action ("Onboard + Print").
        self.assertEqual(action.get("type"), "ir.actions.report")
        self.assertIn("report_name", action)

        # The product was created, barcoded, and stocked in the slot.
        prod = self.env["product.product"].search([("name", "=", "CERT Onboard Tool")], limit=1)
        self.assertTrue(prod, "onboard must create the product")
        self.assertTrue(prod.barcode, "onboard must auto-assign a scannable barcode")
        self.assertTrue(prod.default_code, "onboard must auto-assign a SKU")
        self.assertAlmostEqual(
            self.env["stock.quant"]._get_available_quantity(prod, self.cert_location),
            2.0,
            places=3,
            msg="opening stock must land in the chosen slot",
        )

        # The returned label report renders the new product's label (HTML, to
        # avoid the wkhtmltopdf-in-TransactionCase hang — see test_cert_label_pdf).
        html, ext = self.env["ir.actions.report"]._render_qweb_html(
            "wms_barcode.action_report_wms_product_label_thermal", prod.ids
        )
        self.assertEqual(ext, "html")
        self.assertIn(
            prod.barcode.encode(), html, "the onboard label must carry the product's barcode"
        )

    def test_onboard_only_skips_print(self):
        """The 'Onboard only' button creates the product but returns a plain
        notification (no PDF), so a keeper who doesn't want a label isn't forced
        through the print path."""
        wiz = self.env["wms.product.onboard"].create(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "CERT Onboard NoPrint",
                            "wms_product_kind": "consumable",
                            "initial_qty": 1.0,
                            "location_id": self.cert_location.id,
                        },
                    )
                ],
            }
        )
        action = wiz.action_onboard_no_print()
        self.assertNotEqual(
            (action or {}).get("type"),
            "ir.actions.report",
            "Onboard-only must not trigger a PDF",
        )
        self.assertTrue(
            self.env["product.product"].search_count([("name", "=", "CERT Onboard NoPrint")]),
            "Onboard-only must still create the product",
        )

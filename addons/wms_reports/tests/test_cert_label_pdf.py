"""UI certification — thermal label render (the print deliverable).

Renders the 100x25mm product & location labels via QWeb and asserts the content
(name + barcode) and that each report is bound to the thermal paperformat.

Why HTML, not a real PDF: Odoo disables wkhtmltopdf PDF conversion under
--test-enable (ir_actions_report.py:1027), and forcing it HANGS inside a
TransactionCase because wkhtmltopdf needs the live HTTP asset server. So this
certifies the label TEMPLATE + paperformat (what the WMS owns); the
HTML->PDF step is infra — the binary's presence is asserted, and a real print
was confirmed on the operator's printer.
"""

from odoo.tests import TransactionCase, tagged
from odoo.tools import find_in_path

from ._cert_roles import CertRolesMixin


@tagged("post_install", "-at_install", "wms", "wms_ui_cert", "wms_cert_pdf")
class TestCertLabelRender(CertRolesMixin, TransactionCase):
    def _html(self, report_xmlid, res_ids):
        html, ext = self.env["ir.actions.report"]._render_qweb_html(report_xmlid, res_ids)
        self.assertEqual(ext, "html")
        return html

    def test_product_label_renders_name_and_barcode(self):
        html = self._html(
            "wms_barcode.action_report_wms_product_label_thermal", self.cert_product.ids
        )
        self.assertIn(b"CERT Widget", html, "product name must appear on the label")
        self.assertIn(self.cert_product.barcode.encode(), html, "the barcode digits must appear")

    def test_location_label_renders_barcode(self):
        html = self._html(
            "wms_barcode.action_report_wms_location_label_thermal", self.cert_location.ids
        )
        self.assertIn(self.cert_location.barcode.encode(), html, "location barcode must appear")

    def test_batch_labels_render_one_per_product(self):
        p2 = self.env["product.product"].create(
            {
                "name": "CERT Widget 2",
                "type": "consu",
                "is_storable": True,
                "barcode": "CERTWIDGET02",
                "wms_product_kind": "consumable",
            }
        )
        html = self._html(
            "wms_barcode.action_report_wms_product_label_thermal",
            (self.cert_product + p2).ids,
        )
        self.assertIn(b"CERTWIDGET01", html)
        self.assertIn(b"CERTWIDGET02", html, "a batch print must include every product's label")

    def test_labels_use_the_thermal_100x25_paperformat(self):
        for action_xmlid in (
            "wms_barcode.action_report_wms_product_label_thermal",
            "wms_barcode.action_report_wms_location_label_thermal",
        ):
            pf = self.env.ref(action_xmlid).paperformat_id
            self.assertTrue(pf, "%s must bind a paperformat" % action_xmlid)
            self.assertEqual(pf.page_width, 100, "label width must be 100mm (4in)")
            self.assertEqual(pf.page_height, 25, "label height must be 25mm (1in)")

    def test_wkhtmltopdf_available_for_conversion(self):
        # Soft infra check: the deployment can convert the rendered HTML to PDF.
        self.assertTrue(
            find_in_path("wkhtmltopdf"),
            "wkhtmltopdf must be installed to print label PDFs",
        )

# -*- coding: utf-8 -*-
"""Direct TSPL label printing: TSPL generation, dry-run send, wizard, security.

The physical send (win32print) is NOT exercised here — CI is Linux and there is
no printer. We test everything up to the wire: the TSPL string is correct, the
wizard builds the right labels for products and locations, the default-printer
rule holds, and unsupported screens are refused. ``wms_print_dry_run`` makes
``print_labels`` return the TSPL instead of sending it.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_direct_print")
class TestDirectPrint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Printer = cls.env["wms.label.printer"]
        cls.printer = cls.Printer.create(
            {
                "name": "Test TE244",
                "connection": "spooler",
                "system_name": "TSC TE244",
                "is_default": True,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Probe Widget",
                "default_code": "PW-1",
                # Alphanumeric (not a 13-digit numeric), so it isn't validated
                # as an EAN-13 by the project's barcode-integrity check.
                "barcode": "WMSPROBE001",
                "type": "consu",
            }
        )
        wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.loc = cls.env["stock.location"].create(
            {
                "name": "Rack 9",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
                "barcode": "R09",
            }
        )

    # ---- TSPL generation -------------------------------------------------
    def test_tspl_has_media_and_barcode(self):
        tspl = self.printer.build_tspl([{"title": "R09", "subtitle": "Rack 9", "barcode": "R09"}])
        self.assertIn("SIZE 100 mm,25 mm", tspl)
        self.assertIn("GAP 3 mm,0 mm", tspl)
        self.assertIn("DENSITY 10", tspl)
        self.assertIn("BARCODE", tspl)
        self.assertIn('"R09"', tspl)
        self.assertIn("PRINT 1,1", tspl)

    def test_copies_in_print_command(self):
        tspl = self.printer.build_tspl([{"barcode": "X1"}], copies=3)
        self.assertIn("PRINT 1,3", tspl)

    def test_output_is_ascii_and_quote_safe(self):
        # Non-ASCII dropped, the double-quote that would break a TSPL literal
        # is replaced — the whole job must be ASCII-encodable.
        tspl = self.printer.build_tspl([{"title": 'Café "Z"', "barcode": "B1"}])
        self.assertNotIn("é", tspl)
        tspl.encode("ascii")  # must not raise

    def test_media_reflows_with_label_size(self):
        self.printer.label_width_mm = 60
        self.printer.label_height_mm = 40
        tspl = self.printer.build_tspl([{"barcode": "B1"}])
        self.assertIn("SIZE 60 mm,40 mm", tspl)

    def test_nothing_to_print_raises(self):
        with self.assertRaises(UserError):
            self.printer.build_tspl([{"title": "", "subtitle": "", "barcode": ""}])

    def test_dry_run_returns_tspl(self):
        out = self.printer.with_context(wms_print_dry_run=True).print_labels([{"barcode": "Z9"}])
        self.assertIsInstance(out, str)
        self.assertIn("SIZE", out)

    # ---- model rules -----------------------------------------------------
    def test_get_default_printer(self):
        self.assertEqual(self.Printer.get_default_printer(), self.printer)

    def test_single_default_enforced(self):
        second = self.Printer.create({"name": "Second", "system_name": "Other", "is_default": True})
        self.printer.invalidate_recordset(["is_default"])
        self.assertTrue(second.is_default)
        self.assertFalse(self.printer.is_default)

    def test_spooler_needs_name(self):
        with self.assertRaises(Exception):
            self.Printer.create({"name": "Bad", "connection": "spooler", "system_name": False})

    # ---- wizard ----------------------------------------------------------
    def _wizard(self, model, ids, **vals):
        return (
            self.env["wms.label.print.wizard"]
            .with_context(
                active_model=model,
                active_ids=ids,
                wms_print_dry_run=True,
            )
            .create({"printer_id": self.printer.id, **vals})
        )

    def test_wizard_product_print(self):
        wiz = self._wizard("product.product", self.product.ids, copies=2)
        res = wiz.action_print()
        self.assertEqual(res["params"]["type"], "success")

    def test_wizard_location_print(self):
        wiz = self._wizard("stock.location", self.loc.ids)
        res = wiz.action_print()
        self.assertEqual(res["params"]["type"], "success")

    def test_wizard_rejects_unsupported_model(self):
        with self.assertRaises(UserError):
            self.env["wms.label.print.wizard"].with_context(
                active_model="res.partner", active_ids=[1]
            ).default_get(["printer_id"])

    def test_wizard_all_without_barcode_raises(self):
        nobc = self.env["product.product"].create({"name": "No Barcode", "type": "consu"})
        wiz = self._wizard("product.product", nobc.ids)
        with self.assertRaises(UserError):
            wiz.action_print()

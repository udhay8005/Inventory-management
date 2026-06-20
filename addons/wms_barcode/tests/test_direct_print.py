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
    def _tspl(self, labels, **kw):
        # no-logo keeps the job pure-ASCII text so assertions are deterministic
        # (the real logo is a binary BITMAP exercised by the wizard tests).
        return self.printer.with_context(wms_print_no_logo=True).build_tspl(labels, **kw)

    def test_tspl_has_media_and_barcode(self):
        tspl = self._tspl([{"title": "R09", "subtitle": "Rack 9", "barcode": "R09"}])
        self.assertIsInstance(tspl, bytes)
        self.assertIn(b"SIZE 100 mm,25 mm", tspl)
        self.assertIn(b"GAP 3 mm,0 mm", tspl)
        self.assertIn(b"DENSITY 10", tspl)
        self.assertIn(b"BARCODE", tspl)
        self.assertIn(b'"R09"', tspl)
        self.assertIn(b"PRINT 1,1", tspl)

    def test_short_uppercase_code_uses_code39(self):
        # Code 39 gives more bars for short codes (the fuller "normal barcode").
        self.assertIn(b'"39"', self._tspl([{"barcode": "R09"}]))

    def test_long_code39_compatible_uses_code39(self):
        # Upper-case structured SKUs are Code39-compatible, so they print as the
        # fuller, wider Code 39 (more bars per char) to fill more of the label
        # beside the big logo — and Code 39 scans more reliably at this density.
        self.assertIn(b'"39"', self._tspl([{"barcode": "MED-CAL-CIP-INJ-100MG-30ML"}]))

    def test_code128_fallback_for_non_code39(self):
        # A value Code 39 can't carry (lower case here) falls back to the compact
        # Code 128 so it still prints and scans.
        self.assertIn(b'"128"', self._tspl([{"barcode": "prod-90210-abc"}]))

    def test_copies_in_print_command(self):
        self.assertIn(b"PRINT 1,3", self._tspl([{"barcode": "X1"}], copies=3))

    def test_barcode_and_digits_fit_within_label(self):
        """Regression: on the 100x25 mm stock the bars + the human-readable SKU
        printed below them (HRI=1) must fit inside the label height. A fixed
        11 mm bar height ignored the offset + that readable line, so the digits
        clipped off the bottom edge into the die-cut gap on real TE244 output."""
        import re

        tspl = self._tspl([{"title": "X", "barcode": "MED-CAL-CIP-INJ-100MG-30ML"}]).decode("ascii")
        m = re.search(r'BARCODE (\d+),(\d+),"[^"]+",(\d+),', tspl)
        self.assertTrue(m, "expected a BARCODE command in the TSPL")
        y, height = int(m.group(2)), int(m.group(3))
        label_dots = round(self.printer.label_height_mm / 25.4 * (self.printer.dpi or 203))
        # bars must end with at least ~3 mm (24 dots) of room below for the HRI
        # digits, or the readable SKU prints off the bottom edge.
        self.assertLessEqual(
            y + height,
            label_dots - 24,
            "barcode bars leave no room for the readable SKU below — it clips",
        )

    def test_output_is_ascii_and_quote_safe(self):
        # Non-ASCII dropped, the double-quote that would break a TSPL literal
        # is replaced. With no logo the job is pure ASCII.
        tspl = self._tspl([{"title": 'Café "Z"', "barcode": "B1"}])
        tspl.decode("ascii")  # must not raise
        self.assertNotIn(b"\xc3", tspl)  # the UTF-8 'é' bytes are gone
        self.assertIn(b"Caf", tspl)

    def test_media_reflows_with_label_size(self):
        self.printer.label_width_mm = 60
        self.printer.label_height_mm = 40
        self.assertIn(b"SIZE 60 mm,40 mm", self._tspl([{"barcode": "B1"}]))

    def test_nothing_to_print_raises(self):
        with self.assertRaises(UserError):
            self._tspl([{"title": "", "subtitle": "", "barcode": ""}])

    def test_non_ascii_barcode_rejected(self):
        # A non-ASCII barcode would be silently truncated by _ascii, so the
        # printed bars would no longer match the stored barcode and fail to scan
        # back. We reject it with a clear error that names the offending char.
        with self.assertRaises(UserError) as cm:
            self._tspl([{"title": "Bad", "barcode": "CAFÉ-01"}])
        msg = str(cm.exception)
        self.assertIn("cannot be printed", msg)  # operator-facing wording
        self.assertIn("É", msg)  # the offending character is named

    def test_smart_paste_artifacts_rejected(self):
        # SKUs pasted from Word/Excel often carry an em dash or a non-breaking
        # space — both are > 0x7E and must be rejected, not silently dropped.
        for bad in ("MED" + chr(0x2014) + "PARA", "MED" + chr(0x00A0) + "PARA"):
            with self.assertRaises(UserError):
                self._tspl([{"title": "Bad", "barcode": bad}])

    def test_quote_in_barcode_rejected(self):
        # A double-quote terminates the TSPL string literal (and _ascii rewrites
        # it to '), so a quoted barcode would print a different code than stored.
        with self.assertRaises(UserError):
            self._tspl([{"title": "Bad", "barcode": 'AB"CD'}])

    def test_control_char_in_barcode_rejected(self):
        with self.assertRaises(UserError):
            self._tspl([{"title": "Bad", "barcode": "AB\tCD"}])

    def test_barcode_boundary_chars(self):
        # Pin the inclusive bounds: 0x7E '~' prints, DEL 0x7F is rejected, so an
        # off-by-one on the range check (e.g. >= 0x7E) would fail this test.
        tspl = self._tspl([{"title": "OK", "barcode": "A~B"}])
        self.assertIn(b'"A~B"', tspl)
        with self.assertRaises(UserError):
            self._tspl([{"title": "Bad", "barcode": "A\x7fB"}])

    def test_ascii_barcode_with_symbols_allowed(self):
        # The structured Business SKU uses hyphens; plain ASCII must still print.
        tspl = self._tspl([{"title": "OK", "barcode": "MED-PARA-CIP-TAB-500MG-10"}])
        self.assertIn(b'"MED-PARA-CIP-TAB-500MG-10"', tspl)

    def test_overlong_barcode_rejected(self):
        # >48 chars would be silently truncated in the TSPL BARCODE payload, so the
        # printed bars would differ from the stored value. Reject up front.
        with self.assertRaises(UserError):
            self._tspl([{"title": "Bad", "barcode": "A" * 49}])

    def test_48char_barcode_allowed(self):
        # 48 chars is the encodable limit and must still print in full.
        code = "A" * 48
        tspl = self._tspl([{"title": "OK", "barcode": code}])
        self.assertIn(('"%s"' % code).encode("ascii"), tspl)

    def test_title_only_label_with_blank_barcode_ok(self):
        # An empty barcode is allowed (title-only labels) — the guard is a no-op.
        tspl = self._tspl([{"title": "Shelf A", "barcode": ""}])
        self.assertIn(b"Shelf A", tspl)

    def test_dry_run_returns_tspl(self):
        out = self.printer.with_context(wms_print_dry_run=True).print_labels([{"barcode": "Z9"}])
        self.assertIsInstance(out, bytes)
        self.assertIn(b"SIZE", out)

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

    def test_wizard_template_print(self):
        """F1: the WMS Products list is product.template, so the wizard must
        accept a template and resolve it to its variant for the label."""
        tmpl = self.product.product_tmpl_id
        wiz = self._wizard("product.template", tmpl.ids)
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

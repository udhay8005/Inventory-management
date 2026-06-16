"""P0 — auto-minted EAN-13 alias is always a valid 13-digit GS1 code.

Guards the silent-no-barcode regression the design review caught:
product_template._next_ean13() returns '' (and then NO wms.barcode.alias
is created) unless the sequence body is exactly 12 digits. The EAN-13
sequence prefix moved from '89011110' (GS1-India 890 registered range) to
'02' (GS1 restricted-circulation, in-house range) with padding widened
4 -> 10 so the body stays 2 + 10 = 12 digits.

These tests assert, on the live sequence, that every newly created WMS
product gets a wms.barcode.alias whose barcode is:
  * exactly 13 digits, all numeric,
  * on the restricted-circulation '02' prefix (not the old 890 range),
  * carrying a correct GS1 check digit.
If anyone re-breaks the 12-digit precondition (e.g. changes the prefix
width without compensating the padding), the alias silently vanishes and
test_new_product_gets_valid_ean13 fails loudly.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_ean13")
class TestEan13Alias(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["product.template"]
        cls.Alias = cls.env["wms.barcode.alias"]

    def _unit_alias(self, tmpl):
        variant = tmpl.product_variant_ids[:1]
        return self.Alias.search(
            [("product_id", "=", variant.id), ("units_per_scan", "=", 1.0)],
            limit=1,
        )

    @staticmethod
    def _checksum(twelve):
        digits = [int(c) for c in twelve]
        total = sum(digits[0::2]) + 3 * sum(digits[1::2])
        return str((10 - (total % 10)) % 10)

    def test_new_product_gets_valid_ean13(self):
        tmpl = self.Template.create({"name": "EAN P0 Tool", "wms_product_kind": "tool"})
        alias = self._unit_alias(tmpl)
        self.assertTrue(
            alias,
            "every new WMS product must get an EAN-13 alias - a blank one means "
            "_next_ean13's 12-digit precondition was broken (silent regression)",
        )
        code = alias.barcode
        self.assertEqual(len(code), 13, "EAN-13 must be exactly 13 digits")
        self.assertTrue(code.isdigit(), "EAN-13 must be all numeric")

    def test_ean13_is_on_restricted_circulation_prefix(self):
        tmpl = self.Template.create({"name": "EAN P0 Feed", "wms_product_kind": "feed"})
        code = self._unit_alias(tmpl).barcode
        self.assertTrue(
            code.startswith("02"),
            "auto EAN-13 must be on the GS1 restricted-circulation '02' range, "
            "not the old GS1-India '890' registered range",
        )
        self.assertFalse(
            code.startswith("890"),
            "auto EAN-13 must NOT use the old GS1-India 890 registered prefix",
        )

    def test_ean13_check_digit_is_valid(self):
        tmpl = self.Template.create({"name": "EAN P0 Med", "wms_product_kind": "medicine"})
        code = self._unit_alias(tmpl).barcode
        self.assertEqual(
            code[-1],
            self._checksum(code[:12]),
            "the 13th digit must be the correct GS1 EAN-13 check digit",
        )

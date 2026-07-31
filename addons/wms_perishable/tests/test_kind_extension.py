"""V20-002 — the new perishable kinds are first-class in the v19 kind machinery
(selectable, expiry-sensitive, SKU prefix + sequence, returnable=False), and the
existing v19 kinds are unchanged (regression).
"""

from odoo.tests import TransactionCase, tagged

_NEW = ("vaccine", "supplement", "chemical", "fertilizer", "food")


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestKindExtension(TransactionCase):
    def _kind_selection(self):
        return dict(
            self.env["product.template"].fields_get(["wms_product_kind"])["wms_product_kind"][
                "selection"
            ]
        )

    def test_new_kinds_are_selectable(self):
        sel = self._kind_selection()
        for k in _NEW:
            self.assertIn(k, sel, "%s must be a selectable WMS kind" % k)

    def test_new_kinds_are_expiry_sensitive(self):
        # Re-import to read the rebound module attribute (extended at load).
        from odoo.addons.wms_location.models.product_template import EXPIRY_SENSITIVE_KINDS

        for k in _NEW:
            self.assertIn(k, EXPIRY_SENSITIVE_KINDS, "%s must be expiry-sensitive" % k)

    def test_new_kind_auto_sku_prefix_and_sequence(self):
        # A bare vaccine product (no code) auto-gets a VAC- SKU from its sequence.
        vac = self.env["product.template"].create(
            {"name": "Cert Vaccine FMD", "wms_product_kind": "vaccine"}
        )
        self.assertTrue(
            vac.default_code and vac.default_code.startswith("VAC-"),
            "vaccine SKU must start with VAC-, got %r" % vac.default_code,
        )
        fert = self.env["product.template"].create(
            {"name": "Cert Urea Fertilizer", "wms_product_kind": "fertilizer"}
        )
        self.assertTrue(fert.default_code.startswith("FERT-"), fert.default_code)
        # fertilizer is weighed → kg UoM seeded
        self.assertEqual(fert.uom_id, self.env.ref("uom.product_uom_kgm"))

    def test_new_kind_returnable_default_false(self):
        for k in _NEW:
            t = self.env["product.template"].create({"name": "Cert %s" % k, "wms_product_kind": k})
            self.assertFalse(t.wms_is_returnable, "%s (perishable) must not be returnable" % k)

    def test_v19_kinds_unchanged(self):
        # Regression: an existing v19 kind still composes its SKU + keeps its
        # returnable default (tool=returnable).
        tool = self.env["product.template"].create(
            {"name": "Cert Drill", "wms_product_kind": "tool"}
        )
        self.assertTrue(tool.default_code.startswith("TOOL-"), tool.default_code)
        self.assertTrue(tool.wms_is_returnable, "tool must stay returnable")

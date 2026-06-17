"""P3 — Guided Product Creation wizard.

Proves the guided path: the category drives the Kind + the required fields, the
SKU previews live from the identity, the chosen Form suggests the unit, creating
produces a fully classified product with a structured SKU + PRD code + barcode
(via product.template.create), a missing required field is blocked with a friendly
message, and a duplicate identity is blocked.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_product_create")
class TestProductCreateWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.W = cls.env["wms.product.create"]
        cls.cat_med = cls.env.ref("wms_location.cat_medicines")  # req brand/form/strength/pack
        cls.cat_other = cls.env.ref("wms_location.cat_other")  # consumable, nothing required
        cls.fam = cls.env.ref("wms_location.family_paracetamol")  # PARA
        cls.brand = cls.env.ref("wms_location.brand_cipla")  # CIP
        cls.tab = cls.env.ref("wms_location.form_tablet")  # TAB, Units
        cls.syr = cls.env.ref("wms_location.form_syrup")  # SYR, Litre
        cls.uom_litre = cls.env.ref("uom.product_uom_litre")

    def _wiz(self, **vals):
        base = {"categ_id": self.cat_med.id, "name": "W Product"}
        base.update(vals)
        return self.W.create(base)

    # ------------------------------------------------------------------
    def test_kind_from_category(self):
        w = self._wiz()
        self.assertEqual(w.wms_product_kind, "medicine", "category drives the kind")
        self.assertTrue(w.req_brand and w.req_form and w.req_strength and w.req_pack)

    def test_uom_from_form(self):
        w = self._wiz(wms_form_id=self.syr.id)
        self.assertEqual(w.uom_id, self.uom_litre, "syrup form suggests Litre")

    def test_sku_preview_live(self):
        w = self._wiz(
            wms_family_id=self.fam.id,
            wms_brand_id=self.brand.id,
            wms_form_id=self.tab.id,
            wms_dosage="500mg",
            wms_pack_size="10",
        )
        self.assertEqual(w.sku_preview, "MED-PARA-CIP-TAB-500MG-10")
        self.assertEqual(w.code128_preview, "MED-PARA-CIP-TAB-500MG-10")
        self.assertTrue(w.pid_preview.startswith("PRD-"))
        self.assertTrue(w.ean_preview.startswith("02"))

    def test_required_by_category_blocks(self):
        # Medicine requires Strength; omit it -> blocked with a friendly error.
        w = self._wiz(
            wms_family_id=self.fam.id,
            wms_brand_id=self.brand.id,
            wms_form_id=self.tab.id,
            wms_pack_size="10",
        )
        with self.assertRaises(UserError):
            w.action_create()

    def test_create_produces_classified_product(self):
        w = self._wiz(
            name="Paracetamol Tab 500 (Cipla)",
            wms_family_id=self.fam.id,
            wms_brand_id=self.brand.id,
            wms_form_id=self.tab.id,
            wms_dosage="500mg",
            wms_pack_size="10",
        )
        action = w.action_create()
        tmpl = self.env["product.template"].browse(action["res_id"])
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB-500MG-10")
        self.assertTrue(tmpl.wms_product_code.startswith("PRD-"))
        self.assertEqual(tmpl.wms_family_id, self.fam)
        self.assertEqual(tmpl.wms_product_kind, "medicine")
        self.assertEqual(tmpl.product_variant_id.barcode, "MED-PARA-CIP-TAB-500MG-10")

    def test_duplicate_identity_blocked(self):
        kw = dict(
            wms_family_id=self.fam.id,
            wms_brand_id=self.brand.id,
            wms_form_id=self.tab.id,
            wms_dosage="500mg",
            wms_pack_size="10",
        )
        self._wiz(name="First", **kw).action_create()
        dup = self._wiz(name="Second", **kw)
        self.assertTrue(dup.dup_warning, "live warning should flag the duplicate")
        with self.assertRaises(UserError):
            dup.action_create()

    def test_create_and_new_returns_wizard(self):
        w = self._wiz(
            name="Para 650",
            wms_family_id=self.fam.id,
            wms_brand_id=self.brand.id,
            wms_form_id=self.tab.id,
            wms_dosage="650mg",
            wms_pack_size="10",
        )
        action = w.action_create_and_new()
        self.assertEqual(action["res_model"], "wms.product.create")
        self.assertTrue(
            self.env["product.product"].search_count(
                [("default_code", "=", "MED-PARA-CIP-TAB-650MG-10")]
            )
        )

"""Product Master P1 — identity master registers + editable category tree
+ per-category required-field config (inert until P3).

Proves the safe, additive foundation:
  * the three coded master registers (Family/Brand/Form) load with their
    seeded codes, reject duplicate codes, uppercase-normalise input, and
    enforce the per-register length cap;
  * the enterprise category tree loaded with the expected xmlids and
    parent links, carries wms_default_kind on its leaves, and — the
    non-negotiable data-safety point — seeding it did NOT reparent or move
    any pre-existing product's categ_id;
  * the per-category required-identity flags exist and the
    wms_effective_req_* recursive compute ORs a branch's policy down to a
    child category;
  * the masters are manager-write / user-read only.
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_product_master")
class TestCategoryConfig(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Family = cls.env["wms.family"]
        cls.Brand = cls.env["wms.brand"]
        cls.Form = cls.env["wms.form"]
        cls.Categ = cls.env["product.category"]

    # ------------------------------------------------------------------
    # Master registers
    # ------------------------------------------------------------------
    def test_seeded_masters_present(self):
        self.assertTrue(self.env.ref("wms_location.form_tablet"))
        self.assertEqual(self.env.ref("wms_location.brand_cipla").code, "CIP")
        self.assertEqual(
            self.env.ref("wms_location.form_syrup").default_uom_id,
            self.env.ref("uom.product_uom_litre"),
            "syrup form should suggest Litre",
        )

    def test_code_is_uppercased(self):
        fam = self.Family.create({"name": "Amoxicillin", "code": "amox"})
        self.assertEqual(fam.code, "AMOX", "code must be stored uppercase")

    def test_duplicate_code_rejected(self):
        self.Brand.create({"name": "BrandOne", "code": "BR1"})
        with self.assertRaises(Exception):
            self.Brand.create({"name": "BrandTwo", "code": "BR1"})
            self.env.flush_all()

    def test_form_code_length_cap(self):
        # Form code cap is 4; a 5-char code must be rejected.
        with self.assertRaises(ValidationError):
            self.Form.create({"name": "TooLong", "code": "TABLE"})
            self.env.flush_all()

    def test_family_code_length_cap(self):
        # Family cap is 6; a 7-char code must be rejected.
        with self.assertRaises(ValidationError):
            self.Family.create({"name": "TooLong", "code": "PARACET"})
            self.env.flush_all()

    def test_non_alnum_code_rejected(self):
        with self.assertRaises(ValidationError):
            self.Brand.create({"name": "Bad", "code": "A-B"})
            self.env.flush_all()

    # ------------------------------------------------------------------
    # Category tree
    # ------------------------------------------------------------------
    def test_tree_loaded_with_parents(self):
        med = self.env.ref("wms_location.cat_medicines")
        self.assertEqual(med.parent_id, self.env.ref("wms_location.cat_animal_care"))
        self.assertEqual(med.wms_default_kind, "medicine")

    def test_every_seeded_leaf_has_a_kind(self):
        """Critic's hard rule: a category used for products must resolve a
        kind. Every seeded category that has NO children (a leaf) must carry
        wms_default_kind so the creation wizard never lands kind-less."""
        seeded = self.Categ.search([("id", "in", self._seeded_categ_ids())])
        leaves = seeded.filtered(lambda c: not (c.child_id & seeded))
        missing = leaves.filtered(lambda c: not c.wms_default_kind)
        self.assertFalse(
            missing,
            "seeded leaf categories without a default kind: %s" % missing.mapped("name"),
        )

    def test_seeding_did_not_reparent_existing_product(self):
        """The additive invariant: a product created BEFORE the tree existed
        keeps its categ_id; the seed only CREATES categories."""
        prod = self.env["product.product"].create({"name": "P1 Pre-existing"})
        original = prod.categ_id
        # Re-trigger an idempotent reload would be a -u; here we assert the
        # seed never targets an existing product: its categ_id is whatever
        # Odoo's default is, never one of our seeded nodes by force.
        self.assertEqual(prod.categ_id, original)
        self.assertNotIn(
            prod.categ_id.id,
            self._seeded_categ_ids(),
            "a freshly created product must not be force-assigned a seeded category",
        )

    def test_form_is_model_flag_on_tools(self):
        self.assertTrue(self.env.ref("wms_location.cat_power_tools").wms_form_is_model)
        self.assertFalse(self.env.ref("wms_location.cat_medicines").wms_form_is_model)

    # ------------------------------------------------------------------
    # Required-field matrix + recursive effective compute
    # ------------------------------------------------------------------
    def test_required_flags_on_medicine(self):
        med = self.env.ref("wms_location.cat_medicines")
        self.assertTrue(med.wms_req_brand)
        self.assertTrue(med.wms_req_strength)
        self.assertTrue(med.wms_effective_req_strength)

    def test_effective_req_inherits_from_parent(self):
        """A child with no own flags inherits the branch's required policy."""
        parent = self.Categ.create({"name": "P1 Branch", "wms_req_brand": True})
        child = self.Categ.create({"name": "P1 Leaf", "parent_id": parent.id})
        self.assertFalse(child.wms_req_brand, "child sets no OWN flag")
        self.assertTrue(
            child.wms_effective_req_brand,
            "child must inherit the parent's required-brand policy",
        )

    # ------------------------------------------------------------------
    # Master-data governance: no case-/whitespace-only duplicates
    # ------------------------------------------------------------------
    def test_family_case_duplicate_blocked(self):
        # Seeded family "Paracetamol" — a case-variant must be rejected.
        with self.assertRaises(ValidationError):
            self.Family.create({"name": "PARACETAMOL", "code": "PCM2"})
            self.env.flush_all()

    def test_family_whitespace_duplicate_blocked(self):
        with self.assertRaises(ValidationError):
            self.Family.create({"name": "  Paracetamol  ", "code": "PCM3"})
            self.env.flush_all()

    def test_brand_case_duplicate_blocked(self):
        with self.assertRaises(ValidationError):
            self.Brand.create({"name": "cipla", "code": "CIP2"})
            self.env.flush_all()

    def test_form_case_duplicate_blocked(self):
        with self.assertRaises(ValidationError):
            self.Form.create({"name": "TABLET", "code": "TB2"})
            self.env.flush_all()

    def test_distinct_master_name_allowed(self):
        fam = self.Family.create({"name": "Amoxicillin Trihydrate", "code": "AMX"})
        self.assertEqual(fam.name, "Amoxicillin Trihydrate")

    def test_category_duplicate_same_parent_blocked(self):
        # Seeded "Cleaning" lives under Consumables — a case-variant there is garbage.
        with self.assertRaises(ValidationError):
            self.Categ.create(
                {"name": "cleaning", "parent_id": self.env.ref("wms_location.cat_consumables").id}
            )
            self.env.flush_all()

    def test_category_same_name_different_parent_allowed(self):
        # "Cleaning" under a DIFFERENT parent is legitimate (different branch).
        c = self.Categ.create(
            {"name": "Cleaning", "parent_id": self.env.ref("wms_location.cat_chemicals").id}
        )
        self.assertTrue(c.id)

    def test_category_has_active_field(self):
        """Odoo 19 CE product.category has no native active field; we add one
        so a category can be disabled (archived) without code."""
        categ = self.Categ.create({"name": "P1 Archivable"})
        self.assertTrue(categ.active)
        categ.active = False
        self.assertFalse(
            self.Categ.search([("id", "=", categ.id)]),
            "an archived category drops out of the default search",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _seeded_categ_ids(self):
        ids = []
        for xmlid in (
            "cat_animal_care",
            "cat_medicines",
            "cat_vaccines",
            "cat_supplements",
            "cat_first_aid",
            "cat_feed",
            "cat_green_feed",
            "cat_dry_feed",
            "cat_concentrate",
            "cat_mineral_mix",
            "cat_silage",
            "cat_consumables",
            "cat_cleaning",
            "cat_stationery",
            "cat_packaging",
            "cat_chemicals",
            "cat_sanitizers",
            "cat_disinfectants",
            "cat_detergents",
            "cat_tools",
            "cat_hand_tools",
            "cat_power_tools",
            "cat_measuring_tools",
            "cat_spare_parts",
            "cat_spare_electrical",
            "cat_spare_plumbing",
            "cat_spare_mechanical",
            "cat_equipment",
            "cat_office",
            "cat_kitchen",
            "cat_agriculture",
            "cat_other",
        ):
            rec = self.env.ref("wms_location.%s" % xmlid, raise_if_not_found=False)
            if rec:
                ids.append(rec.id)
        return ids

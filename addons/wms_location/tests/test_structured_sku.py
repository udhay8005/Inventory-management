"""Product Master P2 — two-identifier scheme + structured Business SKU.

Proves:
  * every product gets an immutable internal code PRD-NNNNNN, unique and
    write-protected forever;
  * the Business SKU (default_code) is composed deterministically from
    Kind + Family + Brand + [Variant] + Form + [Strength] + [Pack] using the
    masters' stable codes + squeezed free text;
  * a product with no Family/Brand falls back to the legacy KIND-NNNNN;
  * a composed SKU that already exists BLOCKS creation (no -2 auto-suffix);
  * the chosen Form suggests the UoM (syrup → L) over the kind default;
  * stock movement FREEZES the SKU + barcode (write blocked), and the
    pre-freeze "regenerate SKU" action recomposes from identity;
  * the soft identity duplicate onchange warns without blocking.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_structured_sku")
class TestStructuredSku(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["product.template"]
        cls.Product = cls.env["product.product"]
        cls.fam = cls.env.ref("wms_location.family_paracetamol")  # PARA
        cls.brand = cls.env.ref("wms_location.brand_cipla")  # CIP
        cls.form_tab = cls.env.ref("wms_location.form_tablet")  # TAB, Units
        cls.form_syr = cls.env.ref("wms_location.form_syrup")  # SYR, Litre
        cls.uom_litre = cls.env.ref("uom.product_uom_litre")
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)

    def _med(self, **extra):
        vals = {
            "name": extra.pop("name", "P2 Med"),
            "wms_product_kind": "medicine",
            "wms_family_id": self.fam.id,
            "wms_brand_id": self.brand.id,
            "wms_form_id": self.form_tab.id,
            # Storable so the freeze tests can place a stock.quant (Odoo 19
            # refuses quants on a non-storable product).
            "type": "consu",
            "is_storable": True,
        }
        vals.update(extra)
        return self.Template.create(vals)

    # ------------------------------------------------------------------
    # Internal product code (PRD)
    # ------------------------------------------------------------------
    def test_prd_code_stamped_on_every_product(self):
        tmpl = self.Template.create({"name": "P2 Plain", "wms_product_kind": "consumable"})
        self.assertTrue(tmpl.wms_product_code, "every product gets an internal code")
        self.assertTrue(tmpl.wms_product_code.startswith("PRD-"))

    def test_prd_code_is_immutable(self):
        tmpl = self._med()
        with self.assertRaises(UserError):
            tmpl.wms_product_code = "PRD-000999"

    def test_prd_code_unique(self):
        a = self._med(name="PRD A")
        with self.assertRaises(Exception):
            b = self._med(name="PRD B")
            b.wms_product_code = a.wms_product_code
            self.env.flush_all()

    # ------------------------------------------------------------------
    # Business SKU composition
    # ------------------------------------------------------------------
    def test_business_sku_composed(self):
        tmpl = self._med(wms_dosage="500 mg", wms_pack_size="10")
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB-500MG-10")

    def test_optional_segments_collapse(self):
        # No variant, no strength, no pack -> they collapse, no empty dashes.
        tmpl = self._med()
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB")

    def test_variant_segment_included(self):
        tmpl = self._med(wms_variant="Adult", wms_pack_size="10")
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-ADUL-TAB-10")

    def test_squeeze(self):
        sq = self.Template._wms_squeeze
        self.assertEqual(sq("500 mg", 5), "500MG")
        self.assertEqual(sq("50kg", 6), "50KG")
        self.assertEqual(sq("Premium", 4), "PREM")
        self.assertEqual(sq("", 4), "")
        self.assertEqual(sq(None, 4), "")

    def test_fallback_to_kind_sequence_without_identity(self):
        tmpl = self.Template.create({"name": "P2 NoIdentity", "wms_product_kind": "consumable"})
        self.assertTrue(
            tmpl.default_code.startswith("CONS-"),
            "without Family/Brand the SKU falls back to the KIND- sequence",
        )

    # ------------------------------------------------------------------
    # Collision = BLOCK (never auto-suffix)
    # ------------------------------------------------------------------
    def test_collision_blocks_creation(self):
        self._med(name="First", wms_pack_size="10")
        with self.assertRaises(UserError):
            self._med(name="Dup", wms_pack_size="10")

    def test_collision_never_auto_suffixes(self):
        a = self._med(name="A", wms_pack_size="10")
        self.assertEqual(a.default_code, "MED-PARA-CIP-TAB-10")
        # A genuinely different pack composes a different SKU and is allowed.
        b = self._med(name="B", wms_pack_size="20")
        self.assertEqual(b.default_code, "MED-PARA-CIP-TAB-20")
        # No product should ever carry an auto-suffixed "-2" code.
        self.assertFalse(self.Product.search([("default_code", "=like", "MED-PARA-CIP-TAB-10-%")]))

    # ------------------------------------------------------------------
    # Form suggests UoM
    # ------------------------------------------------------------------
    def test_form_suggests_uom_over_kind(self):
        # Medicine defaults to Units, but a SYRUP form suggests Litre.
        tmpl = self._med(name="P2 Syrup", wms_form_id=self.form_syr.id)
        self.assertEqual(
            tmpl.uom_id, self.uom_litre, "the syrup form's suggested unit (L) should win"
        )

    # ------------------------------------------------------------------
    # Freeze after stock movement
    # ------------------------------------------------------------------
    def _give_stock(self, tmpl):
        self.env["stock.quant"].sudo().with_context(inventory_mode=True).create(
            {
                "product_id": tmpl.product_variant_ids[:1].id,
                "location_id": self.wh.lot_stock_id.id,
                "quantity": 5.0,
            }
        )

    def test_stock_freezes_sku(self):
        tmpl = self._med(name="P2 Freeze", wms_pack_size="10")
        self.assertFalse(tmpl.wms_sku_frozen, "no stock yet -> not frozen")
        self._give_stock(tmpl)
        self.assertTrue(tmpl.wms_sku_frozen, "stock placed -> frozen")

    def test_frozen_sku_cannot_be_renamed(self):
        tmpl = self._med(name="P2 Lock", wms_pack_size="10")
        self._give_stock(tmpl)
        with self.assertRaises(UserError):
            tmpl.default_code = "MED-PARA-CIP-TAB-99"

    def test_unfrozen_sku_can_change(self):
        tmpl = self._med(name="P2 Open", wms_pack_size="10")
        tmpl.default_code = "MED-PARA-CIP-TAB-11"  # no stock yet -> allowed
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB-11")

    def test_regenerate_sku_recomposes(self):
        tmpl = self._med(name="P2 Regen")
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB")
        tmpl.wms_pack_size = "10"
        tmpl.action_wms_regenerate_sku()
        self.assertEqual(tmpl.default_code, "MED-PARA-CIP-TAB-10")
        self.assertEqual(
            tmpl.product_variant_ids[:1].barcode, "MED-PARA-CIP-TAB-10", "Code128 re-synced"
        )

    def test_regenerate_refused_when_frozen(self):
        tmpl = self._med(name="P2 RegenLock", wms_pack_size="10")
        self._give_stock(tmpl)
        with self.assertRaises(UserError):
            tmpl.action_wms_regenerate_sku()

    # ------------------------------------------------------------------
    # Soft duplicate onchange
    # ------------------------------------------------------------------
    def test_identity_dup_onchange_warns(self):
        self._med(name="Existing", wms_pack_size="10")
        draft = self.Template.new(
            {
                "name": "Draft",
                "wms_product_kind": "medicine",
                "wms_family_id": self.fam.id,
                "wms_brand_id": self.brand.id,
                "wms_form_id": self.form_tab.id,
            }
        )
        res = draft._onchange_wms_identity_dup()
        self.assertTrue(res and res.get("warning"), "matching identity should warn")

    # ------------------------------------------------------------------
    # Review fixes: reliable freeze, in-batch / manual / archived collisions
    # ------------------------------------------------------------------
    def test_freeze_via_update_available_quantity(self):
        """Reliability guard: _update_available_quantity bypasses the stored-
        compute dependency, but the live freeze check must still fire (this is
        the exact path that silently failed before the live-check fix)."""
        tmpl = self._med(name="P2 UAQ", wms_pack_size="10")
        self.env["stock.quant"]._update_available_quantity(
            tmpl.product_variant_ids[:1], self.wh.lot_stock_id, 7.0
        )
        self.assertTrue(
            tmpl._wms_in_circulation(),
            "stock via _update_available_quantity must freeze the product",
        )
        with self.assertRaises(UserError):
            tmpl.product_variant_ids[:1].barcode = "MED-PARA-CIP-TAB-ZZ"

    def test_in_batch_duplicate_blocked_friendly(self):
        """Two rows in ONE create() composing the same SKU raise the friendly
        UserError (not a raw DB IntegrityError)."""
        row = {
            "wms_product_kind": "medicine",
            "wms_family_id": self.fam.id,
            "wms_brand_id": self.brand.id,
            "wms_form_id": self.form_tab.id,
            "wms_pack_size": "10",
        }
        with self.assertRaises(UserError):
            self.Template.create([dict(row, name="Batch A"), dict(row, name="Batch B")])

    def test_manual_duplicate_code_blocked_friendly(self):
        self.Template.create(
            {"name": "Manual A", "wms_product_kind": "consumable", "default_code": "CONS-MAN-1"}
        )
        with self.assertRaises(UserError):
            self.Template.create(
                {"name": "Manual B", "wms_product_kind": "consumable", "default_code": "CONS-MAN-1"}
            )

    def test_archived_collision_blocked_friendly(self):
        """The archive+recreate path the freeze advertises: recreating an
        archived product's identity hits the FRIENDLY block, not a raw error."""
        a = self._med(name="Arch A", wms_pack_size="10")
        a.active = False
        with self.assertRaises(UserError):
            self._med(name="Arch B", wms_pack_size="10")

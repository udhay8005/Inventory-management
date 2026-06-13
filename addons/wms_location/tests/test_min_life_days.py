"""F4 (wms_location side): product.template.wms_min_life_days.

A kind-seeded, stored-but-editable compute (same idiom as
``expected_return_days`` / ``wms_is_returnable``): sanitation / textile /
safety seed to 7, every other (or unset) kind to 0. The admin can override
per product and the override survives a later re-compute, and the value is
mirrored onto product.product as a stored related field so the other wms_*
addons (the approval gate in wms_barcode) can read
``product.wms_min_life_days`` directly off the variant.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_min_life")
class TestWmsMinLifeDays(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["product.template"]
        cls.Product = cls.env["product.product"]
        # ``product.template.create`` runs a post-create hook
        # (_wms_ensure_barcodes) that touches the wms.barcode.alias model
        # defined in wms_barcode. On the live stack that model is always
        # present; in a stripped wms_location-only install it is not, so the
        # tests that need the real create / variant path are gated on it.
        cls.has_barcode = "wms.barcode.alias" in cls.env

    def _new_template(self, vals):
        """Build a product.template exercising the kind-seed compute without
        depending on the wms_barcode post-create hook.

        The compute runs inside ``super().create`` BEFORE _wms_ensure_barcodes,
        so when wms_barcode is absent we use ``new()`` (in-memory, no hook) to
        read the seeded value; on the full stack we use the real ORM create.
        """
        if self.has_barcode:
            return self.Template.create(vals)
        return self.Template.new(vals)

    def test_kind_seeds_seven_for_durable_kinds(self):
        # sanitation / textile / safety are the only kinds seeded to 7.
        for kind in ("sanitation", "textile", "safety"):
            tmpl = self._new_template({"name": "Min-life %s" % kind, "wms_product_kind": kind})
            self.assertEqual(
                tmpl.wms_min_life_days,
                7,
                "kind %r should seed wms_min_life_days to 7" % kind,
            )

    def test_other_kinds_seed_zero(self):
        # A daily-consumed kind (feed) and an unset kind both seed to 0.
        feed = self._new_template({"name": "Min-life feed", "wms_product_kind": "feed"})
        self.assertEqual(feed.wms_min_life_days, 0, "feed should seed to 0 (consumed daily)")
        unset = self._new_template({"name": "Min-life unset"})
        self.assertEqual(unset.wms_min_life_days, 0, "no kind should seed to 0")

    def test_kind_change_reseeds(self):
        # safety (7) -> feed (0): the compute fires on the kind change.
        tmpl = self._new_template({"name": "Reseed probe", "wms_product_kind": "safety"})
        self.assertEqual(tmpl.wms_min_life_days, 7)
        # On the real-create path the safety kind auto-stamped a SAFE- SKU; the
        # _check_sku_prefix constraint would (correctly) reject keeping it while
        # the kind becomes feed, so clear default_code alongside the kind change
        # exactly as the Admin would — the SKU regenerates from the feed
        # sequence and the min-life compute is what we're actually asserting.
        tmpl.write({"wms_product_kind": "feed", "default_code": False})
        self.assertEqual(tmpl.wms_min_life_days, 0, "kind change to feed should re-seed to 0")

    def test_admin_override_survives_recompute(self):
        if not self.has_barcode:
            self.skipTest("needs the real create path (wms_barcode not installed)")
        # Seeded to 7 from textile; admin lowers it to 3.
        tmpl = self.Template.create({"name": "Override probe", "wms_product_kind": "textile"})
        self.assertEqual(tmpl.wms_min_life_days, 7)
        tmpl.wms_min_life_days = 3
        # An unrelated re-compute must NOT clobber the override (only a kind
        # change re-seeds). Touch an unrelated tracked field to force a flush.
        tmpl.wms_is_returnable = not tmpl.wms_is_returnable
        tmpl.invalidate_recordset(["wms_min_life_days"])
        self.assertEqual(
            tmpl.wms_min_life_days,
            3,
            "admin override must persist; only a kind change re-seeds",
        )

    def test_variant_related_mirror(self):
        if not self.has_barcode:
            self.skipTest("needs the real create path (wms_barcode not installed)")
        # The stored related on product.product reflects the template value
        # and is writable from the variant side.
        tmpl = self.Template.create({"name": "Mirror probe", "wms_product_kind": "sanitation"})
        variant = tmpl.product_variant_ids[:1]
        self.assertTrue(variant, "template should have at least one variant")
        self.assertEqual(
            variant.wms_min_life_days,
            7,
            "variant related mirror should reflect the template seed",
        )
        # Writing through the variant updates the template (store=True,
        # readonly=False related).
        variant.wms_min_life_days = 5
        self.assertEqual(
            tmpl.wms_min_life_days,
            5,
            "writing the variant related mirror should update the template",
        )

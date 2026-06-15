"""F2 — UoM by product kind.

Proves the create-time UoM seeding and the onboard-wizard onchange:
  * a Fluid product is created with uom_id = Litre, a Feed with kg, a
    Tool with Units;
  * a Medicine product gets Units, NOT a Volume/millilitre UoM — this
    protects Scan Issue's photo-required gate, which forces a photo
    whenever the product's UoM category is not "Units";
  * a product created WITH an explicit uom_id keeps it (the create
    override never clobbers a caller-supplied UoM);
  * the onboard line onchange sets Units for a Tool row and Litre for a
    Fluid row, and re-picking the kind always re-drives the UoM (the kind
    wins, so the operator settles the kind first, then adjusts the UoM);
  * the onboard UoM dropdown is restricted to warehouse units (count /
    weight / volume / length / area) — Time / Energy / imperial units are
    excluded.

The create override + KIND_DEFAULT_UOM live in wms_location; the
onboard onchange lives in wms_barcode. Both are exercised here so the
end-to-end "kind picks the UoM, operator can override to Metre" story
is covered in one place.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_uom_kind")
class TestUomByKind(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["product.template"]
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_litre = cls.env.ref("uom.product_uom_litre")
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.uom_meter = cls.env.ref("uom.product_uom_meter")

    # ------------------------------------------------------------------
    # Create-time seeding (wms_location product.template.create override)
    # ------------------------------------------------------------------
    def test_fluid_seeds_litre(self):
        tmpl = self.Template.create({"name": "F2 Oil", "wms_product_kind": "fluid"})
        self.assertEqual(
            tmpl.uom_id,
            self.uom_litre,
            "a Fluid product should default to Litre (Volume)",
        )

    def test_feed_seeds_kg(self):
        tmpl = self.Template.create({"name": "F2 Bran", "wms_product_kind": "feed"})
        self.assertEqual(
            tmpl.uom_id,
            self.uom_kg,
            "a Feed product should default to kg (Weight)",
        )

    def test_tool_seeds_units(self):
        tmpl = self.Template.create({"name": "F2 Hammer", "wms_product_kind": "tool"})
        self.assertEqual(
            tmpl.uom_id,
            self.uom_unit,
            "a Tool product should default to Units",
        )

    def test_medicine_seeds_units_not_volume(self):
        """Medicine MUST land on Units, never Litre / millilitre — a
        Volume UoM would (where the photo-gate is wired) flip every vet
        injection into Scan Issue's photo-required path. Asserted on the
        UoM record itself because Odoo 19 CE dropped uom.uom.category_id
        in favour of the relative_uom_id chain, so there is no category
        xmlid to compare against."""
        tmpl = self.Template.create({"name": "F2 Vaccine", "wms_product_kind": "medicine"})
        self.assertEqual(
            tmpl.uom_id,
            self.uom_unit,
            "Medicine should default to Units (vials counted; dosage in wms_dosage)",
        )
        self.assertNotEqual(
            tmpl.uom_id,
            self.uom_litre,
            "Medicine must NOT default to Litre (Volume)",
        )
        self.assertNotEqual(
            tmpl.uom_id,
            self.env.ref("uom.product_uom_milliliter"),
            "Medicine must NOT default to millilitre (Volume)",
        )

    def test_medicine_protects_photo_gate(self):
        """The photo-gate (_compute_photo_required) forces a photo when a
        planned product's UoM is "measured, not counted". By landing
        Medicine on the very same Units UoM the gate treats as counted,
        F2 keeps every vet injection OFF that gate. Assert the gate-
        relevant property at the product level: a Medicine's seeded UoM
        equals the Units UoM the gate uses as its reference, and is not
        a Volume UoM. (A full wizard issue is not exercised here because
        wms.scan.issue requires a populated audit trail — taken_by /
        ordered_by / storekeeper_id / usage_note — which is orthogonal
        to the UoM-by-kind behaviour under test.)"""
        med = self.Template.create({"name": "F2 Med Gate", "wms_product_kind": "medicine"})
        self.assertEqual(
            med.uom_id,
            self.uom_unit,
            "Medicine must sit on the Units UoM the photo-gate treats as counted",
        )
        self.assertNotIn(
            med.uom_id,
            self.uom_litre | self.env.ref("uom.product_uom_milliliter"),
            "Medicine must not be a Volume UoM that would arm the photo-gate",
        )

    def test_explicit_uom_is_kept(self):
        """When the caller supplies uom_id, the kind default must NOT
        override it (create-time seed only fills a blank UoM)."""
        tmpl = self.Template.create(
            {
                "name": "F2 Bulk Disinfectant",
                "wms_product_kind": "fluid",
                "uom_id": self.uom_unit.id,
            }
        )
        self.assertEqual(
            tmpl.uom_id,
            self.uom_unit,
            "an explicit uom_id must survive the create-time seed",
        )

    def test_changing_kind_does_not_flip_existing_uom(self):
        """The seed is create-time only: re-classifying an existing
        product never silently flips its UoM (which Odoo blocks once
        stock exists). Re-classify Tool -> Fluid, supplying a matching
        FL- SKU so the kind/SKU-prefix constraint passes and we isolate
        the UoM behaviour: the UoM must stay on the original Units, not
        jump to Litre."""
        tmpl = self.Template.create({"name": "F2 Reclass", "wms_product_kind": "tool"})
        self.assertEqual(tmpl.uom_id, self.uom_unit)
        tmpl.write({"wms_product_kind": "fluid", "default_code": "FL-90001"})
        self.assertEqual(
            tmpl.uom_id,
            self.uom_unit,
            "changing the kind on an existing product must not flip its UoM to Litre",
        )

    def test_helper_returns_kind_uom(self):
        tmpl = self.Template.create({"name": "F2 Helper", "wms_product_kind": "feed"})
        self.assertEqual(
            tmpl._wms_default_uom_id(),
            self.uom_kg.id,
            "_wms_default_uom_id should resolve the kind's UoM id",
        )

    # ------------------------------------------------------------------
    # Onboard wizard line onchange (wms_barcode)
    # ------------------------------------------------------------------
    def test_onboard_onchange_seeds_units_for_tool(self):
        Line = self.env["wms.product.onboard.line"]
        line = Line.new({"name": "OB Tool", "wms_product_kind": "tool"})
        line._onchange_wms_product_kind_uom()
        self.assertEqual(
            line.uom_id,
            self.uom_unit,
            "onboard onchange should seed Units for a Tool row",
        )

    def test_onboard_onchange_seeds_litre_for_fluid(self):
        Line = self.env["wms.product.onboard.line"]
        line = Line.new({"name": "OB Oil", "wms_product_kind": "fluid"})
        line._onchange_wms_product_kind_uom()
        self.assertEqual(
            line.uom_id,
            self.uom_litre,
            "onboard onchange should seed Litre for a Fluid row",
        )

    def test_onboard_kind_change_drives_uom(self):
        """Picking — or re-picking — the kind always drives the UoM, so the
        unit follows the chosen kind (the operator's explicit request). For cut
        pipe / cloth the operator re-picks Metre AFTER settling the kind."""
        Line = self.env["wms.product.onboard.line"]
        line = Line.new({"name": "OB Reclass", "wms_product_kind": "fluid"})
        line._onchange_wms_product_kind_uom()
        self.assertEqual(line.uom_id, self.uom_litre, "Fluid -> Litre")
        line.wms_product_kind = "feed"
        line._onchange_wms_product_kind_uom()
        self.assertEqual(
            line.uom_id, self.uom_kg, "re-picking the kind (Feed) re-drives the UoM to kg"
        )

    def test_onboard_uom_dropdown_is_warehouse_only(self):
        """The UoM dropdown is restricted to warehouse units; Time / Energy /
        imperial units are excluded so operators are not shown Minutes / kWh.
        Uses a real wizard line (not .new()) so the M2M holds real records."""
        wiz = self.env["wms.product.onboard"].create(
            {"line_ids": [(0, 0, {"name": "OB W", "wms_product_kind": "tool"})]}
        )
        allowed = wiz.line_ids.allowed_uom_ids
        self.assertIn(self.uom_unit, allowed)
        self.assertIn(self.uom_kg, allowed)
        self.assertIn(self.uom_litre, allowed)
        self.assertNotIn(self.env.ref("uom.product_uom_hour"), allowed)
        self.assertNotIn(self.env.ref("uom.product_uom_kwh"), allowed)

    def test_onboard_flow_creates_product_with_metre(self):
        """Full onboard path: a plumbing row with Metre creates a product
        carrying Metre (operator override flows through _do_onboard)."""
        wiz = self.env["wms.product.onboard"].create(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "OB Pipe By Length",
                            "wms_product_kind": "plumbing",
                            "initial_qty": 0,
                            "uom_id": self.uom_meter.id,
                        },
                    )
                ]
            }
        )
        wiz._validate()
        wiz._do_onboard()
        product = self.env["product.product"].search([("name", "=", "OB Pipe By Length")], limit=1)
        self.assertTrue(product, "the onboard run should have created the product")
        self.assertEqual(
            product.uom_id,
            self.uom_meter,
            "operator's Metre pick should reach the created product",
        )

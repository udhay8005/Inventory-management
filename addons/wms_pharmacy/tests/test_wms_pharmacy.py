# File: tests/test_wms_pharmacy.py
# Module: wms_pharmacy
# Description: Comprehensive test suite for the pharmacy packaging engine.
#              Covers: packaging hierarchy computed field + constraint,
#              packaging barcode resolve(), dispense tablet accounting,
#              open-package optimisation, strip-level FEFO lot selection,
#              and animal medication history.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: wms_perishable, wms_barcode, wms_pharmacy

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_pharmacy")
class TestWmsPharmacy(TransactionCase):
    """Pharmacy packaging engine — unit + integration tests.

    All tests use ``post_install`` so every dependent addon is fully loaded.
    The ``-at_install`` tag prevents running during module load (avoids a
    partially-configured registry).

    Stock is given to lots via ``stock.quant._update_available_quantity`` which
    is the canonical ORM method. Lots have a far-future expiration_date
    (now + 400 days) to clear the V20-022 short-dated-at-issue guard in
    wms_perishable.

    See addons/wms_perishable/models/product_template.py for the V20-003
    auto-lot-track rule: medicine kind products get ``tracking='lot'`` on
    creation.
    """

    @classmethod
    def setUpClass(cls):
        """Create shared fixtures: warehouse, location, product, lots, animal."""
        super().setUpClass()

        # --- Warehouse & location -------------------------------------------
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.location = cls.warehouse.lot_stock_id  # main storage

        # --- Packaged medicine product (1 variant, lot-tracked) -------------
        # wms_perishable.create sets tracking='lot' automatically for 'medicine'.
        # We must set wms_is_packaged + counts BEFORE creation so the constraint
        # does not fire on a temporary packaged+zero-count state.
        # Note: SKU prefix check requires default_code starts with 'MED-';
        # we set it explicitly to satisfy _check_sku_prefix.
        cls.product_tmpl = cls.env["product.template"].create(
            {
                "name": "Oxytetracycline 500mg",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "default_code": "MED-OXY500",
                "wms_is_packaged": True,
                "wms_tablets_per_strip": 10,
                "wms_strips_per_box": 5,
                # Use the default Units UoM (1 unit = 1 tablet in pharma context).
            }
        )
        # Use the single auto-created product.product variant.
        cls.product = cls.product_tmpl.product_variant_ids[0]

        # --- A second packaged medicine for FEFO tests ----------------------
        cls.product_tmpl2 = cls.env["product.template"].create(
            {
                "name": "Amoxicillin 250mg",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "default_code": "MED-AMOX250",
                "wms_is_packaged": True,
                "wms_tablets_per_strip": 8,
                "wms_strips_per_box": 4,
            }
        )
        cls.product2 = cls.product_tmpl2.product_variant_ids[0]

        # --- Animal -----------------------------------------------------------
        cls.animal = cls.env["wms.animal"].create({"name": "Gauri", "tag": "G-001"})

        # --- Far-future expiry sentinel (avoids V20-022 guard) --------------
        cls.exp_far = fields.Datetime.now() + timedelta(days=400)
        cls.exp_medium = fields.Datetime.now() + timedelta(days=200)
        cls.exp_near = fields.Datetime.now() + timedelta(days=50)

    # =========================================================================
    # 1. Packaging hierarchy — computed field + constraint
    # =========================================================================

    def test_tablets_per_box_computed(self):
        """wms_tablets_per_box = tablets_per_strip * strips_per_box (stored, computed)."""
        self.assertEqual(
            self.product_tmpl.wms_tablets_per_box,
            50,  # 10 * 5
            "tablets_per_box should be 10*5=50",
        )

    def test_tablets_per_box_zero_when_strip_is_zero(self):
        """wms_tablets_per_box is 0 when tablets_per_strip is 0."""
        tmpl = self.env["product.template"].create(
            {
                "name": "Test med zero strip",
                "wms_product_kind": "medicine",
                "default_code": "MED-ZEROSTRIP",
                "wms_is_packaged": False,  # avoid constraint on zero counts
                "wms_tablets_per_strip": 0,
                "wms_strips_per_box": 5,
            }
        )
        self.assertEqual(tmpl.wms_tablets_per_box, 0)

    def test_packaging_constraint_fires(self):
        """wms_is_packaged=True with zero counts raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.env["product.template"].create(
                {
                    "name": "Bad packaged med",
                    "wms_product_kind": "medicine",
                    "default_code": "MED-BAD001",
                    "wms_is_packaged": True,
                    "wms_tablets_per_strip": 0,  # INVALID
                    "wms_strips_per_box": 5,
                }
            )

    def test_packaging_constraint_not_fired_when_not_packaged(self):
        """No constraint when wms_is_packaged=False, even with zero counts."""
        tmpl = self.env["product.template"].create(
            {
                "name": "Non-packaged med",
                "wms_product_kind": "medicine",
                "default_code": "MED-NOTPKG",
                "wms_is_packaged": False,
                "wms_tablets_per_strip": 0,
                "wms_strips_per_box": 0,
            }
        )
        self.assertFalse(tmpl.wms_is_packaged)

    # =========================================================================
    # 2. Packaging barcode resolve()
    # =========================================================================

    def _make_pharma_barcode(self, product, tier, barcode):
        """Helper: create a wms.pharma.packaging.barcode row."""
        return self.env["wms.pharma.packaging.barcode"].create(
            {"product_id": product.id, "tier": tier, "barcode": barcode}
        )

    def test_resolve_box_barcode(self):
        """resolve() for a box barcode returns kind='pharma', tier='box',
        base_units=tablets_per_box."""
        self._make_pharma_barcode(self.product, "box", "PHB-OXY-BOX-T01")
        result = self.env["wms.pharma.packaging.barcode"].resolve("PHB-OXY-BOX-T01")
        self.assertEqual(result["kind"], "pharma")
        self.assertEqual(result["tier"], "box")
        self.assertEqual(result["base_units"], 50)  # 10*5
        self.assertEqual(result["product"].id, self.product.id)

    def test_resolve_strip_barcode(self):
        """resolve() for a strip barcode returns base_units=tablets_per_strip."""
        self._make_pharma_barcode(self.product, "strip", "PHB-OXY-STRIP-T01")
        result = self.env["wms.pharma.packaging.barcode"].resolve("PHB-OXY-STRIP-T01")
        self.assertEqual(result["kind"], "pharma")
        self.assertEqual(result["tier"], "strip")
        self.assertEqual(result["base_units"], 10)

    def test_resolve_tablet_barcode(self):
        """resolve() for a tablet barcode returns base_units=1."""
        self._make_pharma_barcode(self.product, "tablet", "PHB-OXY-TAB-T01")
        result = self.env["wms.pharma.packaging.barcode"].resolve("PHB-OXY-TAB-T01")
        self.assertEqual(result["kind"], "pharma")
        self.assertEqual(result["tier"], "tablet")
        self.assertEqual(result["base_units"], 1)

    def test_resolve_unknown_barcode(self):
        """resolve() returns kind=None for an unregistered barcode."""
        result = self.env["wms.pharma.packaging.barcode"].resolve("DOES-NOT-EXIST-9999")
        self.assertIsNone(result["kind"])

    def test_resolve_empty_string(self):
        """resolve() returns kind=None for an empty string."""
        result = self.env["wms.pharma.packaging.barcode"].resolve("")
        self.assertIsNone(result["kind"])

    # =========================================================================
    # Helpers: stock provisioning
    # =========================================================================

    def _create_lot(self, product, name, expiry):
        """Create a stock.lot with the given expiration_date."""
        return self.env["stock.lot"].create(
            {
                "product_id": product.id,
                "name": name,
                "expiration_date": expiry,
            }
        )

    def _give_stock(self, product, location, quantity, lot):
        """Add stock quant for (product, location, lot) via ORM helper."""
        self.env["stock.quant"]._update_available_quantity(product, location, quantity, lot_id=lot)

    def _make_wizard(self, product, location, quantity, animal=None, note=""):
        """Create a wms.dispense.wizard record (doesn't run dispense)."""
        vals = {
            "product_id": product.id,
            "location_id": location.id,
            "quantity": quantity,
            "note": note,
        }
        if animal:
            vals["animal_id"] = animal.id
        return self.env["wms.dispense.wizard"].create(vals)

    # =========================================================================
    # 3. Basic dispense: tablet count, strips opened, genealogy log, animal link
    # =========================================================================

    def test_dispense_basic_deducts_correct_tablet_count(self):
        """action_dispense() deducts exactly `quantity` tablets from stock."""
        lot = self._create_lot(self.product, "LOT-BASIC-01", self.exp_far)
        self._give_stock(self.product, self.location, 100, lot)

        before = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.location.id),
                ("lot_id", "=", lot.id),
            ]
        )
        qty_before = sum(q.quantity for q in before)

        wiz = self._make_wizard(self.product, self.location, 7)
        wiz.action_dispense()

        after = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.location.id),
                ("lot_id", "=", lot.id),
            ]
        )
        qty_after = sum(q.quantity for q in after)
        self.assertAlmostEqual(
            qty_before - qty_after,
            7,
            places=2,
            msg="Stock should decrease by exactly 7 tablets",
        )

    def test_dispense_creates_genealogy_log(self):
        """action_dispense() creates one wms.dispense.log row."""
        lot = self._create_lot(self.product, "LOT-LOG-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        logs_before = self.env["wms.dispense.log"].search_count(
            [("product_id", "=", self.product.id)]
        )
        wiz = self._make_wizard(self.product, self.location, 3, animal=self.animal)
        wiz.action_dispense()

        logs_after = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(
            self.env["wms.dispense.log"].search_count([("product_id", "=", self.product.id)]),
            logs_before + 1,
        )
        # The log row should have the correct values
        log = logs_after
        self.assertEqual(log.product_id.id, self.product.id)
        self.assertEqual(log.lot_id.id, lot.id)
        self.assertEqual(log.animal_id.id, self.animal.id)
        self.assertEqual(log.quantity, 3)
        self.assertEqual(log.tablets_per_strip, 10)  # snapshot
        self.assertEqual(log.tablets_per_box, 50)  # snapshot

    def test_dispense_links_animal_medication_history(self):
        """Dispense log is accessible via animal.dispense_log_ids and count increments."""
        lot = self._create_lot(self.product, "LOT-ANML-01", self.exp_far)
        self._give_stock(self.product, self.location, 30, lot)

        count_before = self.animal.wms_medication_count
        wiz = self._make_wizard(self.product, self.location, 5, animal=self.animal)
        wiz.action_dispense()

        self.animal.invalidate_recordset(["wms_medication_count", "dispense_log_ids"])
        self.assertEqual(self.animal.wms_medication_count, count_before + 1)
        self.assertIn(
            self.product.id,
            self.animal.dispense_log_ids.mapped("product_id").ids,
        )

    def test_dispense_tracks_strips_opened_correctly(self):
        """Strips opened counter is correct when dispensing from sealed strips.

        Dispense 7 tablets from a 10-tablets-per-strip product:
        - No open strip exists → 1 sealed strip is opened.
        - 3 tablets remain as an open strip.
        """
        lot = self._create_lot(self.product, "LOT-STRIPS-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        wiz = self._make_wizard(self.product, self.location, 7)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id), ("lot_id", "=", lot.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.strips_opened, 1, "7 tablets from 10-tab strip = 1 strip opened")

        # Open strip should have 3 tablets remaining
        open_strip = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ],
            limit=1,
        )
        self.assertEqual(open_strip.tablets_remaining, 3)

    def test_dispense_no_strips_opened_when_exact_fit(self):
        """Dispensing exactly tablets_per_strip tablets opens 1 strip, no leftover."""
        lot = self._create_lot(self.product, "LOT-EXACT-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        wiz = self._make_wizard(self.product, self.location, 10)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id), ("lot_id", "=", lot.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.strips_opened, 1)

        # No open strip should remain (10 tablets consumed the whole strip)
        open_strip = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ]
        )
        self.assertFalse(open_strip, "No open strip should remain after exact strip consumption")

    def test_dispense_multiple_strips_opened(self):
        """Dispensing 25 tablets from 10-tab strips opens 3 strips, 5 remain."""
        lot = self._create_lot(self.product, "LOT-MULTI-01", self.exp_far)
        self._give_stock(self.product, self.location, 100, lot)

        wiz = self._make_wizard(self.product, self.location, 25)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id), ("lot_id", "=", lot.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.strips_opened, 3, "ceil(25/10) = 3 strips opened")

        open_strip = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ],
            limit=1,
        )
        self.assertEqual(
            open_strip.tablets_remaining,
            5,
            "3*10 - 25 = 5 tablets left in last strip",
        )

    # =========================================================================
    # 4. Open-package optimisation: uses existing open strip before opening new
    # =========================================================================

    def test_dispense_uses_existing_open_strip(self):
        """When an open strip exists, the wizard draws from it before opening a new strip."""
        lot = self._create_lot(self.product, "LOT-OPEN-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        # Pre-register an open strip with 4 tablets remaining.
        self.env["wms.open.strip"].sudo().create(
            {
                "product_id": self.product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "tablets_remaining": 4,
            }
        )

        # Dispense 3 tablets — should come entirely from the open strip.
        wiz = self._make_wizard(self.product, self.location, 3)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id), ("lot_id", "=", lot.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.strips_opened, 0, "Should come from open strip, no new strip needed")

        # Open strip should have 1 tablet remaining (4 - 3 = 1)
        remaining_strip = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ],
            limit=1,
        )
        self.assertEqual(remaining_strip.tablets_remaining, 1)

    def test_dispense_empties_open_strip_then_opens_new(self):
        """When dispense > open strip, the wizard empties open strip then opens new ones."""
        lot = self._create_lot(self.product, "LOT-MIXED-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        # Open strip: 6 tablets remaining.
        self.env["wms.open.strip"].sudo().create(
            {
                "product_id": self.product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "tablets_remaining": 6,
            }
        )

        # Dispense 14: 6 from open strip, then need 8 more → 1 sealed strip (10),
        # leftover = 10 - 8 = 2.
        wiz = self._make_wizard(self.product, self.location, 14)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id), ("lot_id", "=", lot.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.strips_opened, 1, "8 remaining needs 1 new sealed strip")

        leftover_strip = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ],
            limit=1,
        )
        self.assertEqual(leftover_strip.tablets_remaining, 2, "10 - 8 = 2 tablets left")

    def test_dispense_deletes_open_strip_when_exhausted(self):
        """Open strip record is deleted when all its tablets are dispensed."""
        lot = self._create_lot(self.product, "LOT-EXHAUST-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        self.env["wms.open.strip"].sudo().create(
            {
                "product_id": self.product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "tablets_remaining": 5,
            }
        )

        # Dispense exactly 5 — open strip should be deleted.
        wiz = self._make_wizard(self.product, self.location, 5)
        wiz.action_dispense()

        remaining = self.env["wms.open.strip"].search(
            [
                ("product_id", "=", self.product.id),
                ("lot_id", "=", lot.id),
                ("location_id", "=", self.location.id),
            ]
        )
        self.assertFalse(remaining, "Open strip should be deleted when exhausted")

    def test_open_package_optimisation_same_expiry(self):
        """When two lots have the same expiry, the one with an open strip is preferred."""
        # Both lots expire in exactly 400 days (same timestamp → FEFO tie).
        same_exp = self.exp_far
        lot_no_strip = self._create_lot(self.product, "LOT-TIE-A", same_exp)
        lot_with_strip = self._create_lot(self.product, "LOT-TIE-B", same_exp)
        self._give_stock(self.product, self.location, 50, lot_no_strip)
        self._give_stock(self.product, self.location, 50, lot_with_strip)

        # Register an open strip for lot_with_strip.
        self.env["wms.open.strip"].sudo().create(
            {
                "product_id": self.product.id,
                "lot_id": lot_with_strip.id,
                "location_id": self.location.id,
                "tablets_remaining": 3,
            }
        )

        wiz = self._make_wizard(self.product, self.location, 2)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(
            log.lot_id.id,
            lot_with_strip.id,
            "Open-package optimisation: prefer the lot with an open strip on equal expiry",
        )

    # =========================================================================
    # 5. Strip-level FEFO: earliest-expiry lot drawn first
    # =========================================================================

    def test_fefo_selects_earliest_expiry_lot(self):
        """Wizard always draws from the lot with the earliest expiration_date first."""
        lot_early = self._create_lot(self.product2, "LOT-FEFO-EARLY", self.exp_near)
        lot_late = self._create_lot(self.product2, "LOT-FEFO-LATE", self.exp_far)

        # Both lots have identical quantities.
        self._give_stock(self.product2, self.location, 50, lot_early)
        self._give_stock(self.product2, self.location, 50, lot_late)

        wiz = self._make_wizard(self.product2, self.location, 5)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product2.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(
            log.lot_id.id,
            lot_early.id,
            "FEFO: earliest-expiry lot should be drawn first",
        )

    def test_fefo_skips_quarantined_lots(self):
        """Quarantined lot is excluded even if it is the earliest-expiry lot."""
        lot_quarantine = self._create_lot(self.product, "LOT-QUAR-01", self.exp_near)
        lot_ok = self._create_lot(self.product, "LOT-QUAR-OK", self.exp_far)

        self._give_stock(self.product, self.location, 50, lot_quarantine)
        self._give_stock(self.product, self.location, 50, lot_ok)

        # Put the early lot into quarantine.
        lot_quarantine.wms_lot_state = "quarantine"

        wiz = self._make_wizard(self.product, self.location, 5)
        wiz.action_dispense()

        log = self.env["wms.dispense.log"].search(
            [("product_id", "=", self.product.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(
            log.lot_id.id,
            lot_ok.id,
            "Quarantined lot must be excluded; wizard should pick the available lot",
        )

    def test_dispense_raises_when_no_stock(self):
        """UserError is raised when there is no available stock."""
        # Use a product with no stock at all.
        no_stock_tmpl = self.env["product.template"].create(
            {
                "name": "Empty medicine",
                "wms_product_kind": "medicine",
                "default_code": "MED-EMPTY01",
                "wms_is_packaged": True,
                "wms_tablets_per_strip": 10,
                "wms_strips_per_box": 5,
            }
        )
        no_stock_product = no_stock_tmpl.product_variant_ids[0]
        wiz = self._make_wizard(no_stock_product, self.location, 5)
        with self.assertRaises(UserError):
            wiz.action_dispense()

    def test_dispense_raises_on_insufficient_lot_stock(self):
        """UserError is raised when no single lot has enough tablets."""
        lot = self._create_lot(self.product, "LOT-INSUFF-01", self.exp_far)
        self._give_stock(self.product, self.location, 3, lot)  # only 3 available

        wiz = self._make_wizard(self.product, self.location, 10)
        with self.assertRaises(UserError):
            wiz.action_dispense()

    def test_dispense_raises_on_zero_quantity(self):
        """UserError is raised when quantity <= 0 (constraint on the wizard)."""
        lot = self._create_lot(self.product, "LOT-ZERQTY-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)
        with self.assertRaises(UserError):
            self._make_wizard(self.product, self.location, 0)

    # =========================================================================
    # 6. Animal medication history: dispense_log_ids + count
    # =========================================================================

    def test_animal_medication_count_increments(self):
        """wms_medication_count increments by 1 per dispense linked to the animal."""
        lot = self._create_lot(self.product, "LOT-COUNT-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        before_count = self.animal.wms_medication_count
        # Two separate dispenses for this animal.
        for _ in range(2):
            wiz = self._make_wizard(self.product, self.location, 2, animal=self.animal)
            wiz.action_dispense()

        self.animal.invalidate_recordset(["wms_medication_count"])
        self.assertEqual(
            self.animal.wms_medication_count,
            before_count + 2,
            "wms_medication_count should increment for each dispense linked to the animal",
        )

    def test_animal_dispense_log_ids_populated(self):
        """dispense_log_ids on wms.animal contains entries created by the wizard."""
        lot = self._create_lot(self.product, "LOT-ANMLIDS-01", self.exp_far)
        self._give_stock(self.product, self.location, 50, lot)

        initial_ids = set(self.animal.dispense_log_ids.ids)
        wiz = self._make_wizard(self.product, self.location, 4, animal=self.animal)
        wiz.action_dispense()

        self.animal.invalidate_recordset(["dispense_log_ids"])
        new_ids = set(self.animal.dispense_log_ids.ids) - initial_ids
        self.assertEqual(len(new_ids), 1, "One new log entry should be linked to the animal")

        log = self.env["wms.dispense.log"].browse(list(new_ids)[0])
        self.assertEqual(log.quantity, 4)
        self.assertEqual(log.product_id.id, self.product.id)

    def test_action_view_dispense_logs_returns_action(self):
        """action_view_dispense_logs() returns an act_window filtered to this animal."""
        action = self.animal.action_view_dispense_logs()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "wms.dispense.log")
        self.assertIn(("animal_id", "=", self.animal.id), action["domain"])

    # =========================================================================
    # 7. Packaging barcode collision guard
    # =========================================================================

    def test_barcode_collision_with_product_barcode_rejected(self):
        """Creating a pharma barcode that duplicates a product.product barcode is rejected."""
        # Find an existing product with a barcode in the system.
        product_with_barcode = self.env["product.product"].search(
            [("barcode", "!=", False)], limit=1
        )
        if not product_with_barcode:
            self.skipTest("No product with barcode found to test collision")

        with self.assertRaises(ValidationError):
            self.env["wms.pharma.packaging.barcode"].create(
                {
                    "product_id": self.product.id,
                    "tier": "box",
                    "barcode": product_with_barcode.barcode,
                }
            )

    def test_barcode_must_be_unique_across_tiers(self):
        """The same barcode string cannot be registered for two different tiers."""
        self.env["wms.pharma.packaging.barcode"].create(
            {
                "product_id": self.product.id,
                "tier": "box",
                "barcode": "PHB-DUPL-TEST-01",
            }
        )
        with self.assertRaises(Exception):  # UNIQUE constraint -> IntegrityError / ValidationError
            self.env["wms.pharma.packaging.barcode"].create(
                {
                    "product_id": self.product.id,
                    "tier": "strip",
                    "barcode": "PHB-DUPL-TEST-01",  # same barcode, different tier
                }
            )

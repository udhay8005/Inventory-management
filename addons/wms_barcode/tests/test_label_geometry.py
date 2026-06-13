"""F6 — label geometry hardening.

Two guarantees:

  * the scannability constraint on wms.label.config rejects a barcode box
    narrower than the 203 DPI floor (40 mm wide / 8 mm tall) and accepts the
    shipped 74 x 12 mm default; and
  * the 19.0.1.30.0 post-migration realigns a saved profile that was mis-set
    logo-RIGHT / barcode-LEFT back to the canonical logo-LEFT / barcode-RIGHT
    geometry, is idempotent on a re-run, and leaves a correctly-configured
    logo-LEFT profile untouched.
"""

import importlib.util
import os

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

# Import the migration module directly from its version folder. The folder name
# is not a valid Python identifier, so it is loaded by path rather than a normal
# `from ... import` (the migrations/ dir is not a Python package).
_MIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "migrations",
    "19.0.1.30.0",
    "post-migration.py",
)
_spec = importlib.util.spec_from_file_location("wms_f6_post_migration", _MIG_PATH)
_f6_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_f6_migration)


@tagged("post_install", "-at_install", "wms", "wms_label_geometry")
class TestLabelGeometry(TransactionCase):
    # ------------------------------------------------------------------
    # Scannability constraint
    # ------------------------------------------------------------------
    def test_narrow_barcode_rejected(self):
        """A 20 mm barcode box is below the 40 mm 203 DPI floor -> rejected."""
        with self.assertRaises(ValidationError):
            self.env["wms.label.config"].create(
                {
                    "name": "F6 too narrow",
                    "barcode_width_mm": 20.0,
                }
            )

    def test_short_barcode_rejected(self):
        """A 5 mm tall barcode box is below the 8 mm floor -> rejected."""
        with self.assertRaises(ValidationError):
            self.env["wms.label.config"].create(
                {
                    "name": "F6 too short",
                    "barcode_height_mm": 5.0,
                }
            )

    def test_default_barcode_accepted(self):
        """The shipped 74 x 12 mm default clears both floors."""
        cfg = self.env["wms.label.config"].create(
            {
                "name": "F6 default-ok",
                "barcode_width_mm": 74.0,
                "barcode_height_mm": 12.0,
            }
        )
        self.assertEqual(cfg.barcode_width_mm, 74.0)
        self.assertEqual(cfg.barcode_height_mm, 12.0)

    def test_shrinking_existing_profile_rejected(self):
        """The constraint fires on write, not only on create."""
        cfg = self.env["wms.label.config"].create({"name": "F6 shrink"})
        with self.assertRaises(ValidationError):
            cfg.write({"barcode_width_mm": 20.0})

    # ------------------------------------------------------------------
    # 19.0.1.30.0 migration — realign mis-set profiles
    # ------------------------------------------------------------------
    def _mis_set_profile(self):
        """A 100 x 25 mm profile mis-configured logo-RIGHT / barcode-LEFT.

        Logo dragged to x = 76 (right edge) and barcode pulled to x = 1 (left
        inch) — the exact inversion the migration repairs. barcode_width stays
        above the scannability floor so the row saves cleanly.
        """
        return self.env["wms.label.config"].create(
            {
                "name": "F6 mis-set logo-RIGHT",
                "paper_width_mm": 100.0,
                "paper_height_mm": 25.0,
                "logo_x_mm": 76.0,
                "logo_y_mm": 1.0,
                "logo_width_mm": 23.0,
                "logo_height_mm": 23.0,
                "title_x_mm": 1.0,
                "subtitle_x_mm": 1.0,
                "barcode_x_mm": 1.0,
                "barcode_y_mm": 9.0,
                "barcode_width_mm": 74.0,
                "barcode_height_mm": 12.0,
            }
        )

    def _normal_profile(self):
        """A correctly-configured logo-LEFT / barcode-RIGHT 100 x 25 profile."""
        return self.env["wms.label.config"].create(
            {
                "name": "F6 normal logo-LEFT",
                "paper_width_mm": 100.0,
                "paper_height_mm": 25.0,
                "logo_x_mm": 1.0,
                "barcode_x_mm": 26.0,
                "barcode_width_mm": 74.0,
                "barcode_height_mm": 12.0,
            }
        )

    def test_migration_realigns_mis_set_row(self):
        bad = self._mis_set_profile()
        _f6_migration.migrate(self.cr, "19.0.1.30.0")
        bad.invalidate_recordset()
        # Logo back in the left inch, barcode back on the right.
        self.assertEqual(bad.logo_x_mm, 1.0)
        self.assertEqual(bad.barcode_x_mm, 26.0)
        self.assertEqual(bad.title_x_mm, 26.0)
        self.assertEqual(bad.subtitle_x_mm, 26.0)
        self.assertEqual(bad.barcode_width_mm, 74.0)
        self.assertEqual(bad.barcode_height_mm, 12.0)

    def test_migration_is_idempotent(self):
        bad = self._mis_set_profile()
        _f6_migration.migrate(self.cr, "19.0.1.30.0")
        bad.invalidate_recordset()
        first = (bad.logo_x_mm, bad.barcode_x_mm)
        # Re-run: the row now reads logo-LEFT, so nothing should change.
        _f6_migration.migrate(self.cr, "19.0.1.30.0")
        bad.invalidate_recordset()
        self.assertEqual((bad.logo_x_mm, bad.barcode_x_mm), first)
        self.assertEqual(bad.logo_x_mm, 1.0)
        self.assertEqual(bad.barcode_x_mm, 26.0)

    def test_migration_leaves_normal_row_alone(self):
        good = self._normal_profile()
        # Park a non-default barcode_y so we can prove the row was not rewritten.
        good.write({"barcode_y_mm": 8.5})
        _f6_migration.migrate(self.cr, "19.0.1.30.0")
        good.invalidate_recordset()
        self.assertEqual(good.logo_x_mm, 1.0)
        self.assertEqual(good.barcode_x_mm, 26.0)
        self.assertEqual(
            good.barcode_y_mm,
            8.5,
            "a correctly-configured logo-LEFT row must not be rewritten",
        )

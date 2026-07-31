"""F6 — realign any mis-set thermal label profile to logo-LEFT / barcode-RIGHT.

The shipped default geometry already puts the logo in the left ~1 inch
(0-25.4 mm) zone and the barcode + text in the right ~3 inch (25.4-100 mm)
zone, and a fresh install carries those defaults via get_active(). This
migration only repairs an EXISTING saved wms.label.config row that was
manually mis-configured the wrong way round -- logo pushed onto the RIGHT or
the barcode dragged onto the LEFT inch -- on the ~100 x 25 mm sticker.

Detection (on a ~100 x 25 mm paper only):
  * logo_x_mm > 25  -> the logo has been moved out of the left inch, or
  * barcode_x_mm < 13 -> the barcode has been dragged into the logo zone.
Either side being wrong means the label reads logo-RIGHT / barcode-LEFT, so
the whole element set is realigned back to the canonical default mm values
(the same numbers the field defaults use).

Guarded + idempotent:
  * only ~100 x 25 mm profiles are considered, so a site that intentionally
    runs a different (e.g. taller / wider) sticker is left alone;
  * a correctly-configured logo-LEFT row matches neither trigger and is left
    untouched, so a re-run is a no-op;
  * on a fresh install there is no saved row at all (get_active() returns a
    transient default), so this is a pure no-op there.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Canonical logo-LEFT / barcode-RIGHT geometry for the 100 x 25 mm (4 x 1 in)
# sticker -- identical to the wms.label.config field defaults. Logo fills the
# left ~1 inch (1..24 mm); title / sub-line / barcode / human-readable fill the
# right ~3 inch starting at x = 26 mm (26 + 74 = 100 mm exactly).
_CANON_LOGO_LEFT = {
    "logo_x_mm": 1.0,
    "logo_y_mm": 1.0,
    "logo_width_mm": 23.0,
    "logo_height_mm": 23.0,
    "title_x_mm": 26.0,
    "title_y_mm": 1.0,
    "title_width_mm": 74.0,
    "subtitle_x_mm": 26.0,
    "subtitle_y_mm": 5.0,
    "subtitle_width_mm": 74.0,
    "barcode_x_mm": 26.0,
    "barcode_y_mm": 9.0,
    "barcode_width_mm": 74.0,
    "barcode_height_mm": 12.0,
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    profiles = (
        env["wms.label.config"]
        .with_context(active_test=False)
        .search(
            [
                # Only ~100 x 25 mm stickers; leave a deliberately different
                # roll's profile alone.
                ("paper_height_mm", "<=", 30.0),
                "|",
                # Logo pushed out of the left inch ...
                ("logo_x_mm", ">", 25.0),
                # ... or barcode dragged into the logo zone.
                ("barcode_x_mm", "<", 13.0),
            ]
        )
    )
    if not profiles:
        _logger.info(
            "F6: no mis-set label profiles found; logo-LEFT/barcode-RIGHT already in place."
        )
        return
    profiles.write(_CANON_LOGO_LEFT)
    _logger.info(
        "F6: realigned %d label profile(s) to logo-LEFT/barcode-RIGHT.",
        len(profiles),
    )

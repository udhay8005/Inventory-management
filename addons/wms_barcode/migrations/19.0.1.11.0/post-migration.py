import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Mirrors the new 4 x 2 in (101.6 x 50.8 mm) defaults on wms.label.config.
_NEW_LAYOUT = {
    "paper_width_mm": 101.6,
    "paper_height_mm": 50.8,
    "gap_mm": 3.0,
    "logo_x_mm": 79.0,
    "logo_y_mm": 2.0,
    "logo_width_mm": 20.0,
    "logo_height_mm": 11.0,
    "title_x_mm": 3.0,
    "title_y_mm": 3.0,
    "title_width_mm": 73.0,
    "title_size_pt": 13.0,
    "subtitle_x_mm": 3.0,
    "subtitle_y_mm": 15.0,
    "subtitle_width_mm": 73.0,
    "subtitle_size_pt": 10.0,
    "barcode_x_mm": 6.0,
    "barcode_y_mm": 26.0,
    "barcode_width_mm": 90.0,
    "barcode_height_mm": 18.0,
    "human_readable_size_pt": 8.0,
}


def migrate(cr, version):
    """Resize label profiles from the old 4x1 (100x25 mm) layout to the new
    4x2 (101.6x50.8 mm) die-cut layout.

    Only profiles still on a short (< 40 mm tall) sticker are re-laid-out, so a
    site that already customised a taller label keeps its own settings. The
    new gap_mm column defaults to 3 mm via the field default.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    profiles = (
        env["wms.label.config"]
        .with_context(active_test=False)
        .search([("paper_height_mm", "<", 40.0)])
    )
    if not profiles:
        _logger.info("wms_label_config: no short-label profiles to resize.")
        return
    profiles.write(_NEW_LAYOUT)
    _logger.info(
        "wms_label_config: resized %d label profile(s) to 4x2 in.",
        len(profiles),
    )

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# The trust's real stock is True-Ally 100 x 25 mm (4 x 1 in). The 19.0.1.11.0
# migration had wrongly resized profiles to 4 x 2; this restores 4 x 1.
_LAYOUT_4X1 = {
    "paper_width_mm": 100.0,
    "paper_height_mm": 25.0,
    "logo_x_mm": 1.0,
    "logo_y_mm": 1.0,
    "logo_width_mm": 23.0,
    "logo_height_mm": 23.0,
    "title_x_mm": 26.0,
    "title_y_mm": 1.0,
    "title_width_mm": 74.0,
    "title_size_pt": 9.0,
    "subtitle_x_mm": 26.0,
    "subtitle_y_mm": 5.0,
    "subtitle_width_mm": 74.0,
    "subtitle_size_pt": 7.0,
    "barcode_x_mm": 26.0,
    "barcode_y_mm": 9.0,
    "barcode_width_mm": 74.0,
    "barcode_height_mm": 12.0,
    "human_readable_size_pt": 6.0,
}


def migrate(cr, version):
    """Revert label profiles to the True-Ally 100x25 mm (4x1 in) layout.

    Only profiles on a tall (> 40 mm) sticker are reverted, so a site that
    intentionally uses a 2-inch label keeps its own settings.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    profiles = (
        env["wms.label.config"]
        .with_context(active_test=False)
        .search([("paper_height_mm", ">", 40.0)])
    )
    if not profiles:
        _logger.info("wms_label_config: no tall profiles to revert.")
        return
    profiles.write(_LAYOUT_4X1)
    _logger.info("wms_label_config: reverted %d profile(s) to 4x1 (100x25 mm).", len(profiles))

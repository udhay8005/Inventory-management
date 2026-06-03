"""Re-flow existing label configs to the True-Ally 100×25 mm sticker.

Before this version the default ``wms.label.config`` row was created
with ``paper_width_mm = 102.0`` (a rough 4-inch approximation) and the
right-block elements (title / subtitle / barcode) started at
``x = 27.0`` with ``width = 74.0`` — total 101 mm, 1 mm past the
sticker's right edge.

The trust's actual hardware is:
  * Sticker: True-Ally 100 × 25 mm
  * Printer: TSC TE244 @ 203 DPI

So the new defaults are:
  * paper_width_mm = 100.0
  * right-block x = 26.0 (74 mm wide → ends at 100 mm exactly)

This migration nudges any *unmodified* config row over to the new
geometry. Rows the Admin has already customised (paper_width_mm not
equal to the old 102.0, or the right-block x not equal to the old
27.0) are left alone — we don't want to overwrite a deliberate
admin layout.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Re-flow paper width if still at the old 102 default.
    cr.execute(
        """
        UPDATE wms_label_config
           SET paper_width_mm = 100.0
         WHERE paper_width_mm = 102.0
        """
    )
    width_updated = cr.rowcount

    # Re-flow the right-block x offset (title / subtitle / barcode)
    # from 27.0 → 26.0 if still at the old default. Only touch rows
    # where ALL THREE are still 27 — that's the unambiguous "Admin
    # hasn't customised anything" signal. If any of the three has
    # been moved, leave the row alone so we don't wreck a deliberate
    # layout.
    cr.execute(
        """
        UPDATE wms_label_config
           SET title_x_mm = 26.0,
               subtitle_x_mm = 26.0,
               barcode_x_mm = 26.0
         WHERE title_x_mm = 27.0
           AND subtitle_x_mm = 27.0
           AND barcode_x_mm = 27.0
        """
    )
    layout_updated = cr.rowcount

    if width_updated or layout_updated:
        _logger.info(
            "wms_barcode 19.0.1.5.0 migration: re-flowed %d row(s) to "
            "100 mm width, %d row(s) to x=26 right-block (was 102 mm + x=27).",
            width_updated,
            layout_updated,
        )

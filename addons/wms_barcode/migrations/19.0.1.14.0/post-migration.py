"""Backfill the new immutable wms_is_scan_issue flag on pre-existing Scan Issue
pickings so the 24h daily-cap counter keeps counting historical issues across
the upgrade (the cap query now filters on the flag, not the origin string)."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE stock_picking
           SET wms_is_scan_issue = TRUE
         WHERE wms_is_scan_issue IS DISTINCT FROM TRUE
           AND origin LIKE 'Barcode FIFO%'
        """
    )

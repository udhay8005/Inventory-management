"""19.0.1.52.0 — backfill ``wms_is_scan_return`` on historical returns.

The return-integrity fix caps a return at (issued minus already-returned).
Pre-fix Scan Return receipts are only identifiable by their origin string,
so stamp them with the new immutable flag — otherwise the ledger would
under-count past returns and let stock be returned twice.
"""


def migrate(cr, version):
    cr.execute(
        "UPDATE stock_picking SET wms_is_scan_return = TRUE "
        "WHERE origin = 'Barcode scan (return)' "
        "AND COALESCE(wms_is_scan_return, FALSE) = FALSE"
    )

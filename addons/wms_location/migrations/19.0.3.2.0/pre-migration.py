import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """De-duplicate product_product.default_code before the new
    UNIQUE(default_code) constraint is applied (Critical #3).

    Keeps the lowest-id row's SKU and suffixes any later duplicates with
    -DUP<n> so the constraint can be created without error. On a clean
    production database (no products) this is a no-op. Any rows it touches
    are logged so an admin can review and re-code them.
    """
    cr.execute(
        """
        WITH dups AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY default_code ORDER BY id) AS rn
            FROM product_product
            WHERE default_code IS NOT NULL AND default_code <> ''
        )
        UPDATE product_product p
        SET default_code = p.default_code || '-DUP' || d.rn
        FROM dups d
        WHERE p.id = d.id AND d.rn > 1
        """
    )
    if cr.rowcount:
        _logger.warning(
            "wms_location: de-duplicated %d product SKU(s) before applying "
            "UNIQUE(default_code); review and re-code them.",
            cr.rowcount,
        )

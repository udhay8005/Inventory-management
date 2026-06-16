import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Back-fill the immutable internal product code (PRD-NNNNNN) on every
    existing product that doesn't have one yet.

    Purely ADDITIVE: it writes only the new ``wms_product_code`` column and
    never touches ``default_code``, ``barcode``, ``stock.quant``,
    ``stock.move.line`` or ``wms.audit``. Idempotent — a re-run only fills
    rows still missing a code (NULL-only candidate filter), so it is a no-op
    on a database that already has codes. Archived products are included
    (active_test=False) so the whole catalogue gets a stable handle.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = (
        env["product.template"]
        .with_context(active_test=False)
        .search([("wms_product_code", "in", (False, ""))])
    )
    seq = env["ir.sequence"]
    filled = 0
    for tmpl in templates:
        code = seq.next_by_code("wms.product.code")
        if code:
            tmpl.wms_product_code = code
            filled += 1
    if filled:
        _logger.info(
            "wms_location: back-filled %d immutable internal product code(s) (PRD-).",
            filled,
        )

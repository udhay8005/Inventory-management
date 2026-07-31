"""F1 — back-fill stock.picking.wms_department_id from the legacy wms_issued_for
column.

The Scan Issue wizard now captures a structured Department (wms.department); the
old free-selection wms_issued_for is derived from it. Historical Scan Issue
pickings only carry wms_issued_for, so the Consumption Value report (which now
groups by department) would show them under a blank department. This maps each
legacy code to its seeded department via wms.department.legacy_issued_for and
sets wms_department_id where it is still NULL.

ORM-based so tracking / constraints are respected. Idempotent: only rows with a
NULL department and a set wms_issued_for are touched, so a re-run is a no-op.
The historical wms_issued_for values are left untouched (still readable, the
report keeps its legacy column).
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Dept = env["wms.department"].with_context(active_test=False)
    # Map every legacy code to its seeded department via legacy_issued_for.
    # Archived departments are included so historical rows still map.
    by_code = {}
    for dept in Dept.search([]):
        if dept.legacy_issued_for:
            # First seeded department for a code wins (codes are 1:1 in the
            # seed; the guard keeps the back-fill deterministic regardless).
            by_code.setdefault(dept.legacy_issued_for, dept)
    if not by_code:
        _logger.info("F1: no departments with a legacy mapping; nothing to back-fill.")
        return

    pickings = (
        env["stock.picking"]
        .with_context(active_test=False)
        .search(
            [
                ("wms_department_id", "=", False),
                ("wms_issued_for", "!=", False),
            ]
        )
    )
    filled = 0
    for code, dept in by_code.items():
        rows = pickings.filtered(lambda p: p.wms_issued_for == code)
        if rows:
            rows.write({"wms_department_id": dept.id})
            filled += len(rows)
    _logger.info(
        "F1: back-filled %s of %s candidate pickings to departments.",
        filled,
        len(pickings),
    )

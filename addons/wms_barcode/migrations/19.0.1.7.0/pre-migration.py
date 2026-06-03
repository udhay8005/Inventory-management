# -*- coding: utf-8 -*-
"""Pre-migration: grandfather pre-existing WMS pickings before the
audit-trail CHECK constraint lands in 19.0.1.7.0.

Rationale
---------
The new constraint refuses any stock.picking row that has
state='done' AND origin LIKE 'Barcode%' AND wms_storekeeper_id IS NULL,
UNLESS the row is flagged wms_audit_legacy=TRUE.

This pre-migration runs BEFORE the new field is added by the ORM, so we
add the column at SQL level, populate it, then let Odoo's ORM-driven
column creation become an idempotent no-op.

Effect on operators
-------------------
Any pre-existing row missing the storekeeper is preserved but flagged.
Admin can filter Inventory -> Transfers on wms_audit_legacy=True to
review and back-fill manually if desired. The new CHECK fires only on
rows created AFTER this migration.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Idempotent column add. Default FALSE so already-compliant rows
    # remain non-legacy. Re-runnable safely.
    cr.execute(
        """
        ALTER TABLE stock_picking
        ADD COLUMN IF NOT EXISTS wms_audit_legacy BOOLEAN DEFAULT FALSE
        """
    )

    # Flag every pre-existing row that would otherwise violate the
    # upcoming CHECK. We intentionally do NOT back-fill storekeeper from
    # create_uid - silently inventing audit anchors would be worse than
    # marking them legacy.
    cr.execute(
        """
        UPDATE stock_picking
           SET wms_audit_legacy = TRUE
         WHERE state = 'done'
           AND origin LIKE 'Barcode%%'
           AND wms_storekeeper_id IS NULL
           AND (wms_audit_legacy IS DISTINCT FROM TRUE)
        """
    )
    grandfathered = cr.rowcount

    cr.execute(
        """
        SELECT name
          FROM stock_picking
         WHERE wms_audit_legacy = TRUE
         ORDER BY id DESC
         LIMIT 5
        """
    )
    sample = [row[0] for row in cr.fetchall()]

    if grandfathered:
        _logger.warning(
            "[wms_barcode 19.0.1.7.0 migration] Grandfathered %d existing "
            "WMS picking(s) lacking an audit-trail storekeeper. They are "
            "preserved and flagged with wms_audit_legacy=TRUE so the new "
            "CHECK constraint will not refuse them. Sample: %s. "
            "Filter Inventory -> Transfers on wms_audit_legacy to review.",
            grandfathered,
            ", ".join(sample) if sample else "(none)",
        )
    else:
        _logger.info(
            "[wms_barcode 19.0.1.7.0 migration] No pre-existing WMS rows "
            "needed grandfathering. CHECK constraint will land cleanly."
        )

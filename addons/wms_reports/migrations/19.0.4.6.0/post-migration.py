# -*- coding: utf-8 -*-
"""19.0.4.6.0 — harden the Google-Drive DR catalog against duplicate rows.

The daily backup task and the hourly pending-retry sweep write the
``wms_gdrive_backup`` table directly via psql (out of process, so the DR
page survives even when Odoo's HTTP layer is down). Until now that write
was a non-atomic SELECT-then-INSERT with no UNIQUE key, so two racing
writers could leave two catalog rows for the same backup set — duplicating
the one screen a non-technical manager relies on after a disaster.

This de-duplicates any existing rows (keeping the newest per ``set_stamp``
and per ``name``) and THEN creates the partial-unique ``set_stamp`` index
plus the unique ``name`` index. The order is load-bearing: ``CREATE UNIQUE
INDEX`` aborts on a dirty database, so the de-dup must run first.

The work itself lives in ``_harden_gdrive_catalog`` next to the model, which
the model's ``init()`` also calls on every install — fresh installs skip the
migrations/ folder entirely, so ``init()`` is what covers them and this
post-migration is the explicit, version-pinned record for the UPGRADE path
(idempotent: a no-op once the indexes already exist).

NOTE: on the live ``wms`` prod DB this is a pure no-op today — Google Drive
is not connected yet (operator OAuth pending), so the table is empty. The
de-dup is correct-by-construction for when the Drive tier goes live.
"""
import logging

from odoo.addons.wms_reports.models.wms_gdrive_backup import _harden_gdrive_catalog

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _harden_gdrive_catalog(cr)
    _logger.info(
        "wms_reports 19.0.4.6.0: wms_gdrive_backup de-duplicated and "
        "set_stamp/name unique indexes ensured."
    )

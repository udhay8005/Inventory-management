# -*- coding: utf-8 -*-
"""Lightweight operational health endpoint for monitoring systems.

GET /wms/health  ->  JSON { status, db_reachable, last_backup_age_hours,
                            last_drill_age_days, warnings }

Status values: HEALTHY | DEGRADED | CRITICAL
HTTP code:     200 for HEALTHY / DEGRADED, 503 for CRITICAL.

Design constraints (SRE):
  * auth="public" so a monitor can poll without credentials.
  * Reads via sudo() — the payload is deliberately non-sensitive
    (ages + status only; no filenames, paths, secrets, or stack traces).
  * Wrapped so ANY internal error degrades to a minimal CRITICAL
    response — the endpoint must never leak an exception or hang.
  * save_session=False so monitoring hits don't spawn session rows.
"""
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WmsHealthController(http.Controller):

    @http.route(
        "/wms/health",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def wms_health(self, **kw):
        try:
            snapshot = request.env["wms.backup.audit"].sudo()._health_snapshot()
            status = snapshot.get("status", "CRITICAL")
            code = 503 if status == "CRITICAL" else 200
            return request.make_json_response(snapshot, status=code)
        except Exception:  # noqa: BLE001 - health must never leak internals
            _logger.exception("wms_health: snapshot failed")
            return request.make_json_response(
                {"status": "CRITICAL", "detail": "health check failed"},
                status=503,
            )

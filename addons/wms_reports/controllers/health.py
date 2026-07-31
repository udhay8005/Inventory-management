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
  * Optional shared-secret gate: when the ir.config_parameter
    `wms_reports.health_token` is set, callers must present it (via the
    `token` query param or the `X-Health-Token` header). Unset by default,
    so credential-less monitoring keeps working unless an admin opts in.
  * Wrapped so ANY internal error degrades to a minimal CRITICAL
    response — the endpoint must never leak an exception or hang.
  * save_session=False so monitoring hits don't spawn session rows.
"""
import logging

from odoo import http
from odoo.http import request
from odoo.tools import consteq

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
            env = request.env
            # Optional shared-secret gate. When configured, require the token;
            # when unset (default) the endpoint stays open for credential-less
            # monitoring (backward compatible).
            token = env["ir.config_parameter"].sudo().get_param("wms_reports.health_token")
            if token:
                provided = kw.get("token") or request.httprequest.headers.get("X-Health-Token", "")
                if not provided or not consteq(provided, token):
                    return request.make_json_response({"status": "unauthorized"}, status=401)
            snapshot = env["wms.backup.audit"].sudo()._health_snapshot()
            status = snapshot.get("status", "CRITICAL")
            code = 503 if status == "CRITICAL" else 200
            return request.make_json_response(snapshot, status=code)
        except Exception:  # noqa: BLE001 - health must never leak internals
            _logger.exception("wms_health: snapshot failed")
            return request.make_json_response(
                {"status": "CRITICAL", "detail": "health check failed"},
                status=503,
            )

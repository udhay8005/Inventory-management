"""Trust-branded favicon for the Odoo backend.

Odoo 19 dropped the `favicon` field on `res.company` (it lives on
`website.website` now, but we're not running the Website module).
Browsers pull the icon from `/web/static/img/favicon.ico` in the
rendered `<link rel="icon">` tag.

Rather than patch the bundled Odoo source — which would be wiped on
the next `git pull` of `.odoo/` — we register a higher-priority route
at the same URL. Werkzeug's URL map gives explicit controller routes
precedence over the catch-all static-file router, so a request for
the favicon falls into this handler and the bundled Odoo "O" never
gets served.

The image bytes live in an `ir.attachment` named `wms.favicon.image`
(see scripts/_set_branding.py). That keeps the file out of the repo
and lets the Admin re-upload from the desk without touching code.
"""

from __future__ import annotations

import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


# Catch-all of every URL Odoo (or the OS) might ask for. The same image
# is served as both .ico (Windows browsers) and .png (everything else)
# because the bytes work fine cross-format -- and we'd rather not gate
# the trust on whether someone uploaded a real .ico file.
_FAVICON_URLS = [
    "/favicon.ico",
    "/web/static/img/favicon.ico",
    "/web/static/img/odoo-icon-ios.png",
    "/web/static/img/odoo-icon-192.png",
]

# `ir.attachment.name` we look up. Keeping it constant means re-runs of
# the bootstrap script overwrite the same row, no orphans accumulate.
_ATTACHMENT_NAME = "wms.favicon.image"


class WmsFaviconController(http.Controller):
    @http.route(_FAVICON_URLS, type="http", auth="public", csrf=False)
    def wms_favicon(self, **_kwargs):
        """Serve the trust-branded icon, falling back to Odoo's default
        if no upload exists yet so the tab is never iconless."""
        attachment = (
            request.env["ir.attachment"].sudo().search([("name", "=", _ATTACHMENT_NAME)], limit=1)
        )
        if not attachment or not attachment.datas:
            # Let Werkzeug fall back to its 404 / the bundled static file
            # by raising a 404 here. We can't return None from an http
            # route, so we just send the bundled bytes from disk.
            return self._fallback()

        data = base64.b64decode(attachment.datas)
        headers = [
            ("Content-Type", attachment.mimetype or "image/png"),
            # Cache for a day. Browsers stash favicons aggressively
            # anyway; a max-age of zero would just hammer the server.
            ("Cache-Control", "public, max-age=86400"),
            ("Content-Length", str(len(data))),
        ]
        return request.make_response(data, headers=headers)

    def _fallback(self):
        # When the Admin hasn't uploaded a favicon yet, fall through to
        # Odoo's bundled icon by reading the file from disk. Saves the
        # Admin from a missing-icon tab while they get organised.
        try:
            from odoo.modules import get_module_resource

            path = get_module_resource("web", "static", "img", "favicon.ico")
            with open(path, "rb") as f:
                data = f.read()
            return request.make_response(data, [("Content-Type", "image/x-icon")])
        except Exception:  # noqa: BLE001
            _logger.warning("favicon fallback failed; returning 404")
            return request.not_found()

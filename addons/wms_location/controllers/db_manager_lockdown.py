"""Block /web/database/* UI routes for the trust install.

Odoo's `list_db = False` config option only hides the database name
list - it leaves the `/web/database/manager` page reachable and the
Create / Drop / Backup / Restore buttons live. Anyone who reaches the
URL and either guesses the master password or finds it written down
can wipe the database.

The trust manages backups via `scripts/backup-native.ps1` (encrypted
pg_dump). The web manager UI brings no value and a lot of risk, so
we replace its routes with a redirect to the login page.

We inherit Odoo's `Database` controller in addons/web/controllers/
database.py and override BOTH the human-facing GET pages (selector /
manager) AND the destructive POST endpoints (create / duplicate / drop /
backup / restore / change_password). The internal JSON endpoint
/web/database/list (drives the login dropdown) is left working.
"""

from __future__ import annotations

import logging

from odoo import http
from odoo.http import request

try:
    # Odoo 19 module path
    from odoo.addons.web.controllers.database import Database
    from odoo.addons.web.controllers.home import Home
except ImportError:  # pragma: no cover - defensive
    Database = None  # type: ignore[assignment]
    Home = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)


def _blocked():
    """Common response: redirect anyone who lands here to the login
    page with a banner. The trust's actual backup / restore path is
    the PowerShell scripts; the manager UI is dead by policy."""
    _logger.warning(
        "Blocked attempt to reach /web/database/* from %s (ua=%r)",
        request.httprequest.remote_addr,
        request.httprequest.headers.get("User-Agent", "")[:120],
    )
    return request.redirect("/web/login?error=manager_disabled")


if Database is not None:

    class WmsDatabaseLockdown(Database):
        # Override the human-facing pages AND the destructive POST endpoints.
        # The internal JSON endpoint /web/database/list (type=jsonrpc, drives
        # the login dropdown) is NOT touched, so existing flows keep working.
        # Blocking only the GET pages would leave create/drop/restore/backup/
        # duplicate/change_password reachable by a direct POST (guarded solely
        # by the master password) - so we block those too. Backup/restore is
        # CLI-only by policy (scripts/backup-native.ps1 / restore-native.ps1).

        @http.route("/web/database/selector", type="http", auth="none")
        def selector(self, **kw):  # noqa: D401 - inherited signature
            return _blocked()

        @http.route("/web/database/manager", type="http", auth="none")
        def manager(self, **kw):
            return _blocked()

        @http.route("/web/database/create", type="http", auth="none", methods=["POST"], csrf=False)
        def create(self, **kw):
            return _blocked()

        @http.route(
            "/web/database/duplicate", type="http", auth="none", methods=["POST"], csrf=False
        )
        def duplicate(self, **kw):
            return _blocked()

        @http.route("/web/database/drop", type="http", auth="none", methods=["POST"], csrf=False)
        def drop(self, **kw):
            return _blocked()

        @http.route("/web/database/backup", type="http", auth="none", methods=["POST"], csrf=False)
        def backup(self, **kw):
            return _blocked()

        @http.route(
            "/web/database/restore",
            type="http",
            auth="none",
            methods=["POST"],
            csrf=False,
            max_content_length=None,
        )
        def restore(self, **kw):
            return _blocked()

        @http.route(
            "/web/database/change_password", type="http", auth="none", methods=["POST"], csrf=False
        )
        def change_password(self, **kw):
            return _blocked()


if Home is not None:

    class WmsLoginBypass(Home):
        """Skip the login form for already-authenticated users.

        Default Odoo behaviour: typing /web/login in the URL bar while
        a valid session cookie is alive still renders the username +
        password form. That confuses trustees ("am I logged in or
        not?") and invites unnecessary credential typing on a shared
        terminal.

        We short-circuit GET /web/login: if the session is alive and
        no error / signup flow is in play, redirect straight to the
        backend (or wherever ?redirect= points). POST submissions
        and password-reset / error flows fall through to the parent
        implementation so the normal sign-in path still works.
        """

        @http.route()
        def web_login(self, redirect=None, **kw):
            is_get = request.httprequest.method == "GET"
            has_session = bool(request.session.uid)
            # If error / login-failure params are present, the parent
            # needs to render the form with the message - don't skip.
            is_error_flow = any(
                k in kw for k in ("error", "auth_login", "auth_signup_token", "token")
            )
            if is_get and has_session and not is_error_flow:
                target = redirect or "/odoo"
                _logger.info(
                    "Skipping login form for uid=%s -> %s",
                    request.session.uid,
                    target,
                )
                return request.redirect(target)
            return super().web_login(redirect=redirect, **kw)

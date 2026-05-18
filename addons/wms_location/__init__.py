import logging

from . import models, wizards

# `tests` is discovered automatically by Odoo when --test-enable is passed.

_logger = logging.getLogger(__name__)

# -- Default credentials for the auto-created Store Keeper user ------------
# The Admin MUST change the password on first login.
_STOREKEEPER_LOGIN = "storekeeper"
_STOREKEEPER_PASSWORD = "storekeeper"


def _create_default_storekeeper(env):
    """Create a default Store Keeper user on first install.

    Runs as a post_init_hook, so the full module registry (including
    purchase_stock, sale, …) is already loaded — ORM defaults are
    applied for every model, dodging the NOT-NULL-without-DB-default
    quirk on res_partner.group_rfq.

    Idempotent: if a user with this login already exists (e.g. the
    Admin already created one manually, or this is a re-upgrade and
    the hook fires again somehow), nothing is touched.
    """
    Users = env["res.users"].sudo()
    existing = Users.with_context(active_test=False).search(
        [("login", "=", _STOREKEEPER_LOGIN)],
        limit=1,
    )
    if existing:
        _logger.info(
            "wms_location: user %r already exists — skipping default-user creation.",
            _STOREKEEPER_LOGIN,
        )
        return

    storekeeper_group = env.ref("wms_location.group_wms_user")
    internal_group = env.ref("base.group_user")

    Users.create(
        {
            "name": "Store Keeper",
            "login": _STOREKEEPER_LOGIN,
            "password": _STOREKEEPER_PASSWORD,
            "lang": "en_US",
            "notification_type": "inbox",
            "group_ids": [(6, 0, [internal_group.id, storekeeper_group.id])],
        }
    )
    _logger.info(
        "wms_location: created default Store Keeper user "
        "(login=%r) — CHANGE THE PASSWORD VIA Settings → Users.",
        _STOREKEEPER_LOGIN,
    )

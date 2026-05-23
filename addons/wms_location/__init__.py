import logging

from . import controllers, models, wizards

# `tests` is discovered automatically by Odoo when --test-enable is passed.

_logger = logging.getLogger(__name__)

# -- Default credentials for the auto-created Store Keeper user ------------
# The Admin MUST change the password on first login.
_STOREKEEPER_LOGIN = "storekeeper"
_STOREKEEPER_PASSWORD = "storekeeper"


def _create_default_storekeeper(env):
    """Create a default Store Keeper user on first install + grant
    backward-compat capabilities on every upgrade.

    Runs as a post_init_hook on install AND post_load on upgrade, so
    the full module registry is loaded — ORM defaults are applied for
    every model, dodging the NOT-NULL-without-DB-default quirk on
    res_partner.group_rfq.

    Two distinct jobs:

      1. Create the default `storekeeper` Odoo user if missing.
      2. Backfill the five capability sub-groups onto every existing
         res.users that is currently in group_wms_user (the original
         "Store Keeper" role) so behaviour is preserved when this
         module upgrades from the pre-capabilities schema. Without
         this, anyone in group_wms_user would suddenly lose the Scan
         Receipt / Scan Issue / Damage menus until an Admin ticks
         the new boxes.
    """
    Users = env["res.users"].sudo()
    base_group = env.ref("wms_location.group_wms_user")
    internal_group = env.ref("base.group_user")

    # Resolve the 5 sub-groups once. Wrap each lookup so a missing
    # ref doesn't crash the hook (e.g. partial install).
    cap_groups = []
    for xmlid in (
        "wms_location.group_wms_can_scan_receive",
        "wms_location.group_wms_can_scan_issue",
        "wms_location.group_wms_can_file_damage",
        "wms_location.group_wms_can_submit_audit",
        "wms_location.group_wms_can_manage_catalog",
    ):
        try:
            cap_groups.append(env.ref(xmlid))
        except ValueError:
            _logger.warning("wms_location: capability group %r not found", xmlid)

    # --- 1. Default storekeeper user (first-install only) ----------------
    existing_default = Users.with_context(active_test=False).search(
        [("login", "=", _STOREKEEPER_LOGIN)],
        limit=1,
    )
    if existing_default:
        _logger.info(
            "wms_location: user %r already exists — skipping default-user creation.",
            _STOREKEEPER_LOGIN,
        )
    else:
        Users.create(
            {
                "name": "Store Keeper",
                "login": _STOREKEEPER_LOGIN,
                "password": _STOREKEEPER_PASSWORD,
                "lang": "en_US",
                "notification_type": "inbox",
                "group_ids": [
                    (6, 0, [internal_group.id, base_group.id] + [g.id for g in cap_groups]),
                ],
            }
        )
        _logger.info(
            "wms_location: created default Store Keeper user "
            "(login=%r) with all 5 capabilities — CHANGE THE PASSWORD VIA Settings → Users.",
            _STOREKEEPER_LOGIN,
        )

    # --- 2. Backfill capabilities on existing keepers (every upgrade) ---
    if not cap_groups:
        return
    existing_keepers = Users.search([
        ("group_ids", "in", base_group.id),
        # Don't touch Admin - they get capabilities via group_wms_manager.
        ("group_ids", "not in", env.ref("wms_location.group_wms_manager").id),
    ])
    added = 0
    for user in existing_keepers:
        missing = [g.id for g in cap_groups if g not in user.group_ids]
        if missing:
            user.write({"group_ids": [(4, gid) for gid in missing]})
            added += 1
    if added:
        _logger.info(
            "wms_location: backfilled %d capability assignments onto "
            "%d existing Store Keeper user(s).",
            sum(len([g for g in cap_groups if g not in u.group_ids]) for u in existing_keepers) + added,
            added,
        )

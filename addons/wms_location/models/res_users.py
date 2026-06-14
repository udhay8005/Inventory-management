"""Backfill capability sub-groups onto legacy Store Keeper users.

Why this exists
---------------
The capability sub-groups (group_wms_can_*) were introduced after the
trust had already created its shared `storekeeper` Odoo user under
the original group_wms_user role. Without a migration step, that
user would lose the Scan Receipt / Scan Issue / Damage / Audit menus
the next time `wms_location` is upgraded - the menus are now gated
by the new sub-groups, and the existing user has none of them.

`_wms_backfill_capabilities` is called from
security/wms_security.xml via a <function> tag so it runs on every
`-u wms_location` upgrade. It walks every res.users currently in
group_wms_user and adds whichever capability sub-groups they're
missing. Idempotent - re-runs are no-ops once the user is fully
backfilled.

Manager users get the capabilities via group_wms_manager's
implied_ids; we explicitly skip them here so the backfill is not
redundant.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Capability group xmlids backfilled onto legacy keepers. The FOUR
# daily-work capabilities only - Manage Catalog is deliberately NOT here:
# editing the product catalog / labels is an Admin task, and the roster's
# "Create login" action (wms.storekeeper.action_create_login) already grants
# exactly these four with Manage Catalog OFF. Keeping the backfill in sync
# with that means an upgrade never silently re-widens a keeper's power.
# Adding a new daily-work sub-group later: append its xmlid here.
_CAPABILITY_XMLIDS = [
    "wms_location.group_wms_can_scan_receive",
    "wms_location.group_wms_can_scan_issue",
    "wms_location.group_wms_can_file_damage",
    "wms_location.group_wms_can_submit_audit",
]


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _wms_backfill_capabilities(self):
        """Grant every legacy Store Keeper the four daily-work capabilities
        (Scan Receive / Scan Issue / File Damage / Submit Audit).

        Manage Catalog is intentionally excluded (see _CAPABILITY_XMLIDS) so
        an upgrade never re-grants catalog/label editing to keepers. Called
        automatically by security/wms_security.xml on each module upgrade.
        Returns the number of users touched (for logging).
        """
        base = self.env.ref("wms_location.group_wms_user", raise_if_not_found=False)
        manager = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not base:
            _logger.warning(
                "wms_location: group_wms_user not found, skipping " "capability backfill"
            )
            return 0

        cap_groups = []
        for xmlid in _CAPABILITY_XMLIDS:
            g = self.env.ref(xmlid, raise_if_not_found=False)
            if g:
                cap_groups.append(g)
        if not cap_groups:
            return 0

        # Find users in the base role. Exclude managers - they get
        # capabilities via group_wms_manager's implied_ids already.
        domain = [("group_ids", "in", base.id)]
        if manager:
            domain.append(("group_ids", "not in", manager.id))
        users = self.sudo().search(domain)

        touched = 0
        for user in users:
            missing = [g.id for g in cap_groups if g not in user.group_ids]
            if missing:
                user.write({"group_ids": [(4, gid) for gid in missing]})
                touched += 1
        if touched:
            _logger.info(
                "wms_location: backfilled capability sub-groups onto "
                "%d existing Store Keeper user(s).",
                touched,
            )
        return touched

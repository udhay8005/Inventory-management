"""Mixin that surfaces a banner when a Store Keeper just edited a record.

The trust's Admin sometimes opens a Damage / Repair Order / Picking
right after a Store Keeper saved changes. Without a hint, the Admin's
own edits silently overwrite the keeper's work. mail.thread already
logs every change in the chatter, but the Admin would have to scroll
through to spot the recent activity.

This mixin adds:
  * wms_keeper_edit_warning (Boolean, computed) -- True iff the last
    write happened within the last 30 minutes by a user who is in
    group_wms_user but NOT in group_wms_manager.
  * wms_keeper_edit_summary  (Char, computed) -- "Suresh, 4 min ago"
    style label for the banner.

Form views inherit this with a simple `<div class="alert alert-warning"
invisible="not wms_keeper_edit_warning">` block. The Admin can still
save; the warning is informational.
"""

from __future__ import annotations

from datetime import timedelta

from odoo import api, fields, models


# Window after which we stop warning. 30 minutes balances "still
# fresh" against "the keeper went on lunch and the Admin is editing
# an hour later — no surprise to expect anymore".
_WARNING_WINDOW_MINUTES = 30


class WmsKeeperWarningMixin(models.AbstractModel):
    _name = "wms.keeper.warning.mixin"
    _description = "Mixin: warn when a Store Keeper edited recently"

    wms_keeper_edit_warning = fields.Boolean(
        compute="_compute_wms_keeper_edit",
        help="True when the last write_uid is in group_wms_user but "
        "not group_wms_manager AND the write_date is within the "
        "last 30 minutes. Drives the orange 'recently edited' "
        "banner on the form view.",
    )
    wms_keeper_edit_summary = fields.Char(
        compute="_compute_wms_keeper_edit",
        help="Human-readable summary shown in the banner, e.g. "
        "'Suresh saved this 4 minutes ago.'",
    )

    @api.depends("write_uid", "write_date")
    def _compute_wms_keeper_edit(self):
        manager_group = self.env.ref(
            "wms_location.group_wms_manager", raise_if_not_found=False
        )
        user_group = self.env.ref(
            "wms_location.group_wms_user", raise_if_not_found=False
        )
        cutoff = fields.Datetime.now() - timedelta(
            minutes=_WARNING_WINDOW_MINUTES
        )
        for rec in self:
            rec.wms_keeper_edit_warning = False
            rec.wms_keeper_edit_summary = False
            if not rec.write_uid or not rec.write_date:
                continue
            if rec.write_date < cutoff:
                continue
            # The current user looking at the form is the Admin if they
            # are in group_wms_manager. We warn only when the LAST
            # writer was a non-manager keeper — Admin-on-Admin edits
            # don't need the banner.
            if not user_group or user_group not in rec.write_uid.group_ids:
                continue
            if manager_group and manager_group in rec.write_uid.group_ids:
                continue
            elapsed = fields.Datetime.now() - rec.write_date
            minutes = max(1, int(elapsed.total_seconds() // 60))
            rec.wms_keeper_edit_warning = True
            rec.wms_keeper_edit_summary = (
                "%s saved this %d minute%s ago. Review their changes "
                "before saving over them."
            ) % (
                rec.write_uid.name,
                minutes,
                "" if minutes == 1 else "s",
            )

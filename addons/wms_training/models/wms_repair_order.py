# -*- coding: utf-8 -*-
"""Wire Beginner Mode to a real behaviour: a stronger confirmation on the
irreversible Scrap action. The flag lives on res.users (this module); the repair
order lives in wms_repair_damage (a dependency), so we expose a computed mirror
of the current user's flag that the inherited form keys its Scrap buttons off.
"""
from odoo import fields, models


class WmsRepairOrder(models.Model):
    _inherit = "wms.repair.order"

    wms_user_beginner_mode = fields.Boolean(
        string="Current user in Beginner Mode",
        compute="_compute_wms_user_beginner_mode",
        help="Mirrors the current user's WMS Beginner Mode flag so the form can "
        "demand an explicit confirmation on the irreversible Scrap action for "
        "users who are still learning the system.",
    )

    def _compute_wms_user_beginner_mode(self):
        # Per-user, not per-record: read the flag once and stamp the recordset.
        beginner = bool(self.env.user.wms_beginner_mode)
        for rec in self:
            rec.wms_user_beginner_mode = beginner

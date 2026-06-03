# -*- coding: utf-8 -*-
"""Beginner Mode: a per-user toggle that turns on extra in-app guidance.

Defaults ON so a brand-new staff member is guided from their first login;
they can switch it off from their own preferences once comfortable. Views
and warnings key off `wms_beginner_mode` to show hints + stronger
confirmations on risky actions.
"""
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    wms_beginner_mode = fields.Boolean(
        string="WMS Beginner Mode",
        default=True,
        help="When on, the WMS shows extra guidance and beginner-friendly "
        "hints. Turn it off once you are comfortable with the system.",
    )

    # Let every user read + flip their OWN beginner-mode flag from their
    # preferences without needing manager rights (Odoo 19 self-field lists).
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["wms_beginner_mode"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["wms_beginner_mode"]

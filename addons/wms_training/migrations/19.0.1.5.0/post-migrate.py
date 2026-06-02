# -*- coding: utf-8 -*-
"""Apply (and repair) the STEP 7 visual enrichment on upgrade.

Calls the shared, idempotent enrichment in hooks.py. This also REPAIRS the
earlier 19.0.1.3.0 attempt, which appended the block as escaped text (a plain
str concatenated to a Markup body): the shared function strips any prior block
first, then re-appends it correctly.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_visual_enrichment


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_visual_enrichment(env)

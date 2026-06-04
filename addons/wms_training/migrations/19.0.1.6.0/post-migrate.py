# -*- coding: utf-8 -*-
"""Critical #6: resolve guided-tour action-link placeholders on upgrade.

The tours now carry /odoo/action-PENDING-<xmlid> placeholders instead of
hardcoded numeric action ids (which break on a fresh database). This calls the
shared, idempotent resolver in hooks.py.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_tour_action_links


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_tour_action_links(env)

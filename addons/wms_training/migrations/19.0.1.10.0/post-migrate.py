# -*- coding: utf-8 -*-
"""Gaushala issue-dimensions / approvals: apply the noupdate=1 training edits.

guided_tours.xml is noupdate="1", so an existing database never re-reads the
admin-tour body. This inserts the new admin-tour step 9 "Issue dimensions and
approvals" (Department / Purpose / Animal on Scan Issue + the manager-only
Approvals queue) and then re-runs the action-link resolver so the step's two
/odoo/action-PENDING placeholders become live links.

The NEW Department / Returns / Approvals help articles need nothing here: new
records are created on module upgrade even inside a noupdate="1" block.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_issue_dimensions_training, apply_tour_action_links


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_issue_dimensions_training(env)
    apply_tour_action_links(env)

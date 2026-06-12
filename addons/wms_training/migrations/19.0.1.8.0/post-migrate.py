# -*- coding: utf-8 -*-
"""Google Drive backup feature: apply the noupdate=1 training edits on upgrade.

help_articles.xml and guided_tours.xml are noupdate="1", so an existing
database never re-reads the edited bodies. This applies the same changes the
XML now carries for fresh installs — the 4:30 PM backup-time wording and the
admin-tour step 7 "Cloud safety net" — then re-runs the action-link resolver
so the new step's /odoo/action-PENDING placeholder becomes a live link.

The two NEW cloud-backup articles (what-is-cloud-backup,
workflow-cloud-backup-now) need nothing here: new records are created on
module upgrade even inside a noupdate="1" block.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_cloud_backup_training, apply_tour_action_links


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_cloud_backup_training(env)
    apply_tour_action_links(env)

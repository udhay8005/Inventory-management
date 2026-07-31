# -*- coding: utf-8 -*-
"""Offline cloud-backup queue: apply the noupdate=1 training edits on upgrade.

guided_tours.xml is noupdate="1", so an existing database never re-reads the
admin-tour body. This inserts the new admin-tour step 8 "Disaster Recovery
page" (the manager-only DR console + offline-queue view) and then re-runs the
action-link resolver so the step's /odoo/action-PENDING placeholder becomes a
live link.

The NEW offline-queue help article (workflow-cloud-backup-offline-queue) needs
nothing here: new records are created on module upgrade even inside a
noupdate="1" block.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_offline_queue_training, apply_tour_action_links


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_offline_queue_training(env)
    apply_tour_action_links(env)

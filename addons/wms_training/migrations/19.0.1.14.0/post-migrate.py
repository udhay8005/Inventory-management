# -*- coding: utf-8 -*-
"""v19.0.42.0.0: restore the "Visual guide" blocks after the menu-wording
recreate, and re-resolve any guided-tour action links.

The pre-migration deletes the two repair articles so the corrected XML
recreates them. A recreated article carries only its BASE body from the
(noupdate="1") XML — the Visual-guide diagram is appended at runtime by
apply_visual_enrichment, never stored in the XML. Without this step the
recreated ``workflow-repairs`` article would silently lose its diagram, which
is exactly the drop the audit flagged for the earlier 11.0 / 12.0 recreate
migrations.

apply_visual_enrichment is idempotent (it strips any prior block before
re-appending) and only touches the slugs in hooks.PLAN, so running it here
both restores ``workflow-repairs`` and heals any guide dropped by a prior
recreate. apply_tour_action_links re-resolves /odoo/action-PENDING-<xmlid>
placeholders that a freshly recreated body may carry — also idempotent.
"""
from odoo import SUPERUSER_ID, api
from odoo.addons.wms_training.hooks import apply_tour_action_links, apply_visual_enrichment


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    apply_visual_enrichment(env)
    apply_tour_action_links(env)

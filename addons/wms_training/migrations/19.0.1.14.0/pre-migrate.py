# -*- coding: utf-8 -*-
"""v19.0.42.0.0: refresh the two repair help articles whose menu-path wording
referenced "Repair Orders" (title case) while the live menu is "Repair orders".

help_articles.xml is noupdate="1", so a plain ``-u`` never re-reads an existing
article's body. We DELETE the affected articles here (PRE, i.e. before the
module's data load) so the corrected XML recreates them fresh on the SAME
upgrade — the established pattern from the 19.0.1.11.0 / 12.0 menu-rename
migrations.

The companion post-migrate then re-runs apply_visual_enrichment so
``workflow-repairs`` (which carries a Visual-guide block appended at runtime)
gets its diagram back after the recreate — closing the long-standing gap where
a delete/recreate dropped the visual guides with nothing to restore them.

Raw SQL is used deliberately: a pre-migration runs before the module's ORM
models are (re)registered, so ``env['wms.help.article']`` would KeyError here.
"""

# Slugs of every article whose menu-path wording changed this release.
_SLUGS = (
    "keeper-path-repair",
    "workflow-repairs",
)


def migrate(cr, version):
    cr.execute("SELECT id FROM wms_help_article WHERE slug IN %s", (_SLUGS,))
    ids = tuple(row[0] for row in cr.fetchall())
    if not ids:
        return
    # Drop attachments + xmlid bindings, then the records, so the module's
    # noupdate=1 data load recreates them from the corrected XML.
    cr.execute(
        "DELETE FROM ir_attachment WHERE res_model = 'wms.help.article' AND res_id IN %s",
        (ids,),
    )
    cr.execute(
        "DELETE FROM ir_model_data WHERE model = 'wms.help.article' AND res_id IN %s",
        (ids,),
    )
    cr.execute("DELETE FROM wms_help_article WHERE id IN %s", (ids,))

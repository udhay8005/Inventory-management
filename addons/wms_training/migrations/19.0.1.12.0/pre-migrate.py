# -*- coding: utf-8 -*-
"""UX overhaul (v19.0.24.0.0): refresh help articles whose navigation text
referenced the now-renamed menus.

help_articles.xml is noupdate="1", so a plain ``-u`` never re-reads an existing
article's body. This release renamed the "Scan Issue (FIFO)" menu to "Scan Issue"
and the "Repair Orders" menu to "Repair orders", so the step-by-step navigation
lines in a handful of articles drifted out of sync with the live UI.

We DELETE the affected articles here (PRE, i.e. before the module's data load)
so the corrected XML recreates them fresh on the SAME upgrade. Safe: nothing has
a foreign key to wms.help.article (verified), and the slugs/xmlids are recreated
identically so tour/index links still resolve.

Raw SQL is used deliberately: a pre-migration runs before the module's ORM models
are (re)registered, so ``env['wms.help.article']`` would KeyError here.
"""

# Slugs of every article whose menu-path wording changed this release.
_SLUGS = (
    "admin-path-damage-repair-oversight",
    "keeper-path-getting-started",
    "keeper-path-issuing-fifo",
    "keeper-path-daily-routine",
    "workflow-fifo-issuing",
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

# -*- coding: utf-8 -*-
"""FEFO-honesty sweep: refresh the reframed help articles on existing installs.

help_articles.xml is noupdate="1", so a plain ``-u`` never re-reads an existing
article's body. This release reframes the stale "FEFO at the issue picker"
wording to the honest model — issuing always pulls oldest-arrived (FIFO) for
every product (a single issue is one product, expiry is tracked per product, so
there is nothing to expiry-sort at the picker); perishables are rotated via the
Expiry Alerts report.

We DELETE the affected articles here (PRE, i.e. before the module's data load)
so the corrected XML recreates them fresh on the SAME upgrade. Safe: nothing has
a foreign key to wms.help.article (verified), so no rows are orphaned, and the
slugs/xmlids are recreated identically so tour/index links still resolve.

Raw SQL is used deliberately: a pre-migration runs before the module's ORM
models are (re)registered, so ``env['wms.help.article']`` would KeyError here.
"""

# Slugs of every article whose FEFO-at-issue wording was reframed this release.
_SLUGS = (
    "what-is-fifo",
    "what-is-fefo",
    "what-is-a-floor-location",
    "what-is-in-date",
    "what-is-scan-issue",
    "admin-path-stock-flow-fifo-fefo",
    "keeper-path-issuing-fifo",
    "keeper-path-daily-routine",
    "workflow-fifo-issuing",
    "safety-double-check-fefo-medicine",
    "faq-where-is-product",
    "faq-fifo-vs-fefo",
)


def migrate(cr, version):
    cr.execute("SELECT id FROM wms_help_article WHERE slug IN %s", (_SLUGS,))
    ids = tuple(row[0] for row in cr.fetchall())
    if not ids:
        return
    # Drop any attachments + xmlid bindings, then the records, so the module's
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

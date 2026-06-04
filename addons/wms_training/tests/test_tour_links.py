"""Critical #6 - guided-tour action links resolve to live action ids at
install: no hardcoded numeric ids in the seed, no leftover PENDING tokens."""

import re

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_tour")
class TestTourLinks(TransactionCase):
    def test_no_pending_placeholders_remain(self):
        arts = self.env["wms.help.article"].search([("body", "like", "/odoo/action-PENDING-")])
        self.assertFalse(
            arts,
            "guided-tour action placeholders were not resolved at install: %s"
            % arts.mapped("slug"),
        )

    def test_tour_links_point_to_real_actions(self):
        tours = self.env["wms.help.article"].search([("slug", "like", "tour-")])
        self.assertTrue(tours, "expected guided-tour articles to exist")
        ids = set()
        for art in tours:
            ids.update(int(m) for m in re.findall(r"/odoo/action-(\d+)", art.body or ""))
        self.assertTrue(ids, "tours should contain resolved action links")
        for aid in ids:
            self.assertTrue(
                self.env["ir.actions.act_window"].browse(aid).exists(),
                "tour links to a non-existent action id %s" % aid,
            )

"""High - Beginner Mode is now wired to a real behaviour: the repair order
exposes a computed mirror of the current user's flag, which the inherited form
uses to demand a confirmation on the irreversible Scrap. Previously the toggle
existed but nothing keyed off it."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_beginner")
class TestBeginnerModeScrapWiring(TransactionCase):
    def test_user_beginner_mirror_tracks_flag(self):
        product = self.env["product.product"].create({"name": "Beginner Tool", "is_storable": True})
        order = self.env["wms.repair.order"].create({"product_id": product.id, "quantity": 1.0})

        self.env.user.wms_beginner_mode = True
        order.invalidate_recordset(["wms_user_beginner_mode"])
        self.assertTrue(
            order.wms_user_beginner_mode,
            "the form mirror must reflect a beginner user (drives the Scrap confirm)",
        )

        self.env.user.wms_beginner_mode = False
        order.invalidate_recordset(["wms_user_beginner_mode"])
        self.assertFalse(
            order.wms_user_beginner_mode,
            "experienced users must not be flagged as beginners",
        )

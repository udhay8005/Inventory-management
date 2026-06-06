"""Batch 7 — smart /wms/find page. Answers "where is it / how much" for a
product lookup and routes keywords ("low") to a quick list. Open to any WMS
user; denied to everyone else.
"""

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_find")
class TestFind(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.user_admin").write(
            {"group_ids": [(4, cls.env.ref("wms_location.group_wms_user").id)]}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "FIND Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "FINDTEST1",
                "wms_product_kind": "consumable",
            }
        )
        wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.env["stock.quant"]._update_available_quantity(cls.product, wh.lot_stock_id, 6.0)
        cls.env.flush_all()

    def test_find_product_by_barcode(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/find?q=FINDTEST1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("FIND Widget", resp.text)
        self.assertIn("On hand", resp.text)

    def test_find_keyword_low(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/find?q=low")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("reorder level", resp.text)

    def test_find_empty_prompt(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/find")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Find an item", resp.text)

    def test_find_blocked_for_non_user(self):
        user = self.env["res.users"].create(
            {"name": "Plain", "login": "plain_find_user", "password": "plain_find_user_pw"}
        )
        self.assertFalse(user.has_group("wms_location.group_wms_user"))
        self.authenticate("plain_find_user", "plain_find_user_pw")
        resp = self.url_open("/wms/find?q=FINDTEST1")
        self.assertEqual(resp.status_code, 404)

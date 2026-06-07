"""FPAT FX-1: /wms/find alias fallback used the wrong field name and crashed
silently for every auto-generated EAN-13 lookup. Also: the wms.audit accept
needed a row lock for double-Accept safety - covered here at the API level
(true 2-connection race requires HttpCase + threading; this asserts the lock
exists and the in-Python state check sees the post-write state on a second
call).
"""

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx1")
class TestFpatFx1Find(HttpCase):
    def test_find_resolves_an_alias_barcode(self):
        self.env.ref("base.user_admin").write(
            {"group_ids": [(4, self.env.ref("wms_location.group_wms_user").id)]}
        )
        product = self.env["product.product"].create(
            {
                "name": "FX1 Alias Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        alias = self.env["wms.barcode.alias"].create(
            {"product_id": product.id, "barcode": "5901234123457", "units_per_scan": 1.0}
        )
        self.assertTrue(alias, "alias must be created")
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/find?q=5901234123457")
        # Previously: 500 because the controller searched ('name','=', q) on
        # an alias model that has no 'name' field.
        self.assertEqual(resp.status_code, 200)
        self.assertIn("FX1 Alias Probe", resp.text)


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx1")
class TestFpatFx1AuditAcceptIdempotent(TransactionCase):
    def test_double_accept_raises_on_second_call(self):
        """The row lock plus DB-state re-read means a second Accept on the
        same audit (e.g. a double-click) must hit the not-submitted guard
        and raise, never apply the variance delta twice.
        """
        wh = self.env["stock.warehouse"].search([], limit=1)
        floor = self.env["stock.location"].create(
            {
                "name": "FX1 Audit Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "FX1 Audit Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        self.env["stock.quant"]._update_available_quantity(product, floor, 12.0)
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "FX1 Audit Keeper"})
        audit = self.env["wms.audit"].create({"storekeeper_id": keeper.id})
        audit.action_start()  # populates lines from current quants + moves to in_progress
        line = audit.line_ids.filtered(lambda ln: ln.product_id == product)
        self.assertTrue(line, "audit should have populated a line for the seeded product")
        line.counted_qty = 10.0  # variance = -2
        audit.action_submit()
        self.assertEqual(audit.state, "submitted")
        audit.action_review_accept()
        self.assertEqual(audit.state, "reviewed")
        with self.assertRaises(UserError):
            audit.action_review_accept()

"""Critical #1/#5 - the removal planner never crosses to a same-named SIBLING
product (which previously issued the wrong SKU/UoM). It pools strictly within
the scanned product's own template, ordered by the single shared removal
engine (stock.quant._wms_sorted_for_removal)."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_removal")
class TestRemovalEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        # Two DISTINCT medicine products sharing name + kind + a (different)
        # expiry: exactly the old name-widening trap. Different SKUs/templates.
        cls.a = cls.env["product.product"].create(
            {
                "name": "Calcium Bolus",
                "is_storable": True,
                "default_code": "MED-AAA",
                "wms_product_kind": "medicine",
                "wms_expiry_date": "2026-01-01",
            }
        )
        cls.b = cls.env["product.product"].create(
            {
                "name": "Calcium Bolus",
                "is_storable": True,
                "default_code": "MED-BBB",
                "wms_product_kind": "medicine",
                "wms_expiry_date": "2027-01-01",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.a, cls.stock, 10.0)
        cls.env["stock.quant"]._update_available_quantity(cls.b, cls.stock, 10.0)

    def test_planner_never_crosses_to_sibling_product(self):
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.a.id, 5.0, parent_location_id=self.stock.id
        )
        planned = {q.product_id.id for q, _take in plan}
        self.assertEqual(planned, {self.a.id}, "planner must stay within product A")
        self.assertEqual(missing, 0.0)

    def test_scanning_b_plans_only_b(self):
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.b.id, 5.0, parent_location_id=self.stock.id
        )
        planned = {q.product_id.id for q, _take in plan}
        self.assertEqual(planned, {self.b.id})
        self.assertEqual(missing, 0.0)

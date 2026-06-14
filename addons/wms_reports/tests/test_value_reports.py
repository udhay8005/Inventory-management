"""Batch 5 — cost / value reports.

Prove the two SQL views compute money correctly: current stock value =
unit cost x on-hand, and consumption value = unit cost x issued qty. Cost is
read from the company-dependent ``standard_price`` jsonb in SQL.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_value")
class TestValueReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "VAL Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "VAL-TEST Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "VALTEST001",
                "wms_product_kind": "consumable",
            }
        )
        cls.product.standard_price = 10.0
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 8.0)
        cls.env.flush_all()

    def test_stock_value(self):
        # 8 on hand x 10.0 cost = 80.0
        recs = self.env["wms.stock.value.report"].search([("product_id", "=", self.product.id)])
        self.assertTrue(recs, "the product should appear in the stock-value view")
        self.assertAlmostEqual(sum(recs.mapped("qty_on_hand")), 8.0, places=2)
        self.assertAlmostEqual(sum(recs.mapped("unit_cost")), 10.0, places=2)
        self.assertAlmostEqual(sum(recs.mapped("stock_value")), 80.0, places=2)

    def test_consumption_value(self):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": 3.0,
                "last_scan": "VALTEST001",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "value test",
                "storekeeper_id": self.keeper.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "the issue should have created a picking")
        self.env.flush_all()
        # issued 3 x 10.0 cost = 30.0
        recs = self.env["wms.consumption.value.report"].search(
            [("product_id", "=", self.product.id)]
        )
        self.assertTrue(recs, "the issue should appear in the consumption-value view")
        self.assertAlmostEqual(sum(recs.mapped("qty_out")), 3.0, places=2)
        self.assertAlmostEqual(sum(recs.mapped("consumption_value")), 30.0, places=2)

    def test_undone_issue_not_counted_as_consumption(self):
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.undo_minutes", "15")
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": 5.0,
                "last_scan": "VALTEST001",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "value test undo",
                "storekeeper_id": self.keeper.id,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        wiz.picking_id.action_wms_undo()
        self.env.flush_all()
        recs = self.env["wms.consumption.value.report"].search(
            [("product_id", "=", self.product.id)]
        )
        self.assertAlmostEqual(
            sum(recs.mapped("qty_out")),
            0.0,
            places=2,
            msg="an undone issue must not count as consumption",
        )


@tagged("post_install", "-at_install", "wms", "wms_value")
class TestReorderSummaryVendor(TransactionCase):
    """1.4: the Reorder Summary must count each product's reorder_qty under
    exactly ONE preferred vendor - not fan it into every vendor's total when a
    product carries more than one supplierinfo row (the old template join did,
    over-stating the buyer's shopping list)."""

    def test_two_vendor_product_not_double_counted(self):
        v1 = self.env["res.partner"].create({"name": "RS Vendor One"})
        v2 = self.env["res.partner"].create({"name": "RS Vendor Two"})
        product = self.env["product.product"].create(
            {
                "name": "RS Two-Vendor Feed",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        # Two suppliers on the same template; v1 has the lower (preferred) sequence.
        self.env["product.supplierinfo"].create(
            [
                {"product_tmpl_id": product.product_tmpl_id.id, "partner_id": v1.id, "sequence": 1},
                {"product_tmpl_id": product.product_tmpl_id.id, "partner_id": v2.id, "sequence": 2},
            ]
        )
        self.env["wms.forecast"].create({"product_id": product.id, "reorder_qty": 5.0})
        self.env.flush_all()

        rows = self.env["wms.reorder.summary"].search([("partner_id", "in", [v1.id, v2.id])])
        by_partner = {r.partner_id.id: r.total_qty for r in rows}
        self.assertIn(
            v1.id, by_partner, "reorder must land under the preferred (lowest-sequence) vendor"
        )
        self.assertNotIn(
            v2.id, by_partner, "the same product must not also be counted under the second vendor"
        )
        self.assertAlmostEqual(
            by_partner[v1.id], 5.0, places=3, msg="reorder_qty must be counted once, not per-vendor"
        )

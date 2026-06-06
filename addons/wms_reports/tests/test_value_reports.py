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

"""Quick-win B — issued-for classification.

Every Scan Issue now records a structured purpose (Cows / Pooja / Maintenance
/ ...) alongside the free-text note, so the Consumption Value report can total
spend by purpose instead of forcing someone to read prose.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_issued_for")
class TestIssuedFor(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "IF Keeper"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "IF Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "IFTEST0001",
                "wms_product_kind": "consumable",
            }
        )
        cls.product.standard_price = 10.0
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 20.0)
        cls.env.flush_all()

    def _issue(self, qty, purpose):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": "IFTEST0001",
                "taken_by": "T",
                "ordered_by": "O",
                "usage_note": "issued-for test",
                "storekeeper_id": self.keeper.id,
                "issued_for": purpose,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        return wiz.picking_id

    def test_issue_records_purpose_on_picking(self):
        picking = self._issue(4.0, "cows")
        self.assertEqual(picking.wms_issued_for, "cows")

    def test_consumption_value_splits_by_purpose(self):
        self._issue(4.0, "cows")
        self._issue(6.0, "pooja")
        self.env.flush_all()
        recs = self.env["wms.consumption.value.report"].search(
            [("product_id", "=", self.product.id)]
        )
        by = {r.issued_for: r.consumption_value for r in recs}
        # 4 x 10 = 40 for cows, 6 x 10 = 60 for pooja
        self.assertAlmostEqual(by.get("cows", 0.0), 40.0, places=2)
        self.assertAlmostEqual(by.get("pooja", 0.0), 60.0, places=2)

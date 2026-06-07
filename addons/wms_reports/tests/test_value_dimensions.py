"""Quick-win A — money dimensions on the risk reports.

Trustees need value (cost x quantity), not just quantities, for: expired stock
(value at risk), damaged stock (loss value), and dead stock (capital tied up).
This proves all three compute from the product's unit cost.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_value_dim")
class TestValueDimensions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.product = cls.env["product.product"].create(
            {
                "name": "VALDIM Feed",
                "type": "consu",
                "is_storable": True,
                "barcode": "VALDIM0001",
                "wms_product_kind": "feed",  # expiry-sensitive kind
            }
        )
        cls.product.standard_price = 20.0
        cls.product.product_tmpl_id.wms_expiry_date = "2020-01-01"  # already expired
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "VALDIM Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        # Stock sits ON the floor so the damage's source-slot check passes.
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.floor, 5.0)
        cls.env.flush_all()

    def test_expiry_value_at_risk(self):
        rows = self.env["wms.expiry.alert"].search([("product_id", "=", self.product.id)])
        self.assertTrue(rows, "expired product should appear in the expiry view")
        self.assertAlmostEqual(sum(rows.mapped("unit_cost")), 20.0, places=2)
        # 5 on hand x 20.0 cost = 100.0 at risk
        self.assertAlmostEqual(sum(rows.mapped("value_at_risk")), 100.0, places=2)

    def test_damage_loss_value(self):
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "VALDIM Keeper"})
        dmg = self.env["wms.damage"].create(
            {
                "product_id": self.product.id,
                "source_slot_id": self.floor.id,
                "quantity": 3.0,
                "wms_reported_by": "X",
                "wms_authorized_by": "Y",
                "wms_storekeeper_id": keeper.id,
            }
        )
        # FPAT High: damage_value is snapshotted at action_confirm time, NOT
        # computed-each-time. A draft damage records no loss yet.
        self.assertAlmostEqual(dmg.damage_value, 0.0, places=2)
        dmg.action_confirm()
        # 3 x 20.0 = 60.0, frozen onto the row.
        self.assertAlmostEqual(dmg.damage_value, 60.0, places=2)

    def test_dead_stock_value(self):
        fc = self.env["wms.forecast"].create(
            {"product_id": self.product.id, "on_hand": 5.0, "velocity_class": "dead"}
        )
        self.assertAlmostEqual(fc.unit_cost, 20.0, places=2)
        # 5 on hand x 20.0 = 100.0 capital tied up
        self.assertAlmostEqual(fc.stock_value, 100.0, places=2)

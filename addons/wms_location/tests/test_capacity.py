"""Batch 4 — opt-in slot capacity enforcement.

`wms_capacity_units` has always been a soft hint. With the System Parameter
`wms_location.enforce_capacity` set to 1 it becomes a hard guard: a write that
overfills an internal location is refused. Off (the default) nothing changes.
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_capacity")
class TestCapacity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "CAP-TEST Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
                "wms_capacity_units": 5.0,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "CAP-TEST Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "CAPTEST001",
                "wms_product_kind": "consumable",
            }
        )
        cls.Param = cls.env["ir.config_parameter"].sudo()

    def _put(self, qty):
        self.env["stock.quant"]._update_available_quantity(self.product, self.floor, qty)
        self.env.flush_all()

    def test_disabled_by_default_allows_overfill(self):
        self.Param.set_param("wms_location.enforce_capacity", "0")
        self._put(100.0)  # 20x capacity, but enforcement is off -> allowed
        self.assertEqual(self.floor.wms_current_qty, 100.0)

    def test_enabled_allows_up_to_capacity(self):
        self.Param.set_param("wms_location.enforce_capacity", "1")
        self._put(5.0)  # exactly at capacity -> allowed
        self.assertEqual(self.floor.wms_current_qty, 5.0)

    def test_enabled_blocks_overfill(self):
        self.Param.set_param("wms_location.enforce_capacity", "1")
        self._put(4.0)
        with self.assertRaises(ValidationError):
            self._put(2.0)  # 4 + 2 = 6 > capacity 5 -> blocked

    def test_zero_capacity_is_never_enforced(self):
        # A location with no capacity set is exempt even when enforcement is on.
        self.Param.set_param("wms_location.enforce_capacity", "1")
        self.floor.wms_capacity_units = 0.0
        self._put(999.0)
        self.assertEqual(self.floor.wms_current_qty, 999.0)

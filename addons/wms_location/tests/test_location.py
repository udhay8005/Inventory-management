from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms")
class TestWmsLocation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search([], limit=1)
        self.parent = self.warehouse.lot_stock_id

    def _gen_rack(self, code="R-TEST"):
        return (
            self.env["wms.rack.generator"]
            .create({"rack_code": code, "parent_location_id": self.parent.id})
            .action_generate()
        )

    def test_generator_creates_6_dividers_and_18_slots(self):
        self._gen_rack("R-T1")
        rack = self.env["stock.location"].search([
            ("wms_rack_code", "=", "R-T1"),
        ], limit=1)
        dividers = self.env["stock.location"].search([
            ("location_id", "=", rack.id),
            ("wms_location_type", "=", "divider"),
        ])
        self.assertEqual(len(dividers), 6, "rack should have exactly 6 dividers")
        slots = self.env["stock.location"].search([
            ("location_id", "in", dividers.ids),
            ("wms_location_type", "=", "slot"),
        ])
        self.assertEqual(len(slots), 18, "rack should have exactly 18 slots")

    def test_seventh_divider_rejected(self):
        self._gen_rack("R-T2")
        rack = self.env["stock.location"].search([
            ("wms_rack_code", "=", "R-T2"),
        ], limit=1)
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create({
                "name": "D-7",
                "location_id": rack.id,
                "usage": "view",
                "wms_location_type": "divider",
                "wms_divider_number": 7,
            })

    def test_fourth_slot_rejected(self):
        self._gen_rack("R-T3")
        divider = self.env["stock.location"].search([
            ("wms_location_type", "=", "divider"),
            ("location_id.wms_rack_code", "=", "R-T3"),
        ], limit=1)
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create({
                "name": "S-4",
                "location_id": divider.id,
                "usage": "internal",
                "wms_location_type": "slot",
                "wms_slot_number": 4,
            })

    def test_fifo_helper(self):
        self._gen_rack("R-FIFO")
        slots = self.env["stock.location"].search([
            ("wms_location_type", "=", "slot"),
            ("location_id.location_id.wms_rack_code", "=", "R-FIFO"),
        ], limit=3)
        self.assertEqual(len(slots), 3)
        product = self.env["product.product"].create({
            "name": "Demo Widget",
            "type": "product",
        })
        # Two quants with different in_dates
        q1 = self.env["stock.quant"].create({
            "product_id": product.id,
            "location_id": slots[0].id,
            "quantity": 5,
            "in_date": "2025-01-01 10:00:00",
        })
        q2 = self.env["stock.quant"].create({
            "product_id": product.id,
            "location_id": slots[1].id,
            "quantity": 5,
            "in_date": "2025-02-01 10:00:00",
        })
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            product.id, 6,
        )
        self.assertEqual(missing, 0)
        # First quant taken from is the oldest
        self.assertEqual(plan[0][0], q1)
        self.assertEqual(plan[0][1], 5.0)
        self.assertEqual(plan[1][0], q2)
        self.assertEqual(plan[1][1], 1.0)

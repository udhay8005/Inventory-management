from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms")
class TestWmsLocation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env["stock.warehouse"].search([], limit=1)
        self.parent = self.warehouse.lot_stock_id

    def _gen_rack(self, code="R-TEST", dividers_per_level=4):
        return (
            self.env["wms.rack.generator"]
            .create({
                "rack_code": code,
                "parent_location_id": self.parent.id,
                "dividers_per_level": dividers_per_level,
            })
            .action_generate()
        )

    def test_generator_creates_full_hierarchy(self):
        self._gen_rack("R-T1", dividers_per_level=4)
        rack = self.env["stock.location"].search([
            ("wms_rack_code", "=", "R-T1"),
        ], limit=1)
        levels = self.env["stock.location"].search([
            ("location_id", "=", rack.id),
            ("wms_location_type", "=", "level"),
        ])
        dividers = self.env["stock.location"].search([
            ("location_id", "in", levels.ids),
            ("wms_location_type", "=", "divider"),
        ])
        slots = self.env["stock.location"].search([
            ("location_id", "in", dividers.ids),
            ("wms_location_type", "=", "slot"),
        ])
        self.assertEqual(len(levels), 6, "should have 6 levels")
        self.assertEqual(len(dividers), 6 * 4, "should have 24 dividers (6×4)")
        self.assertEqual(len(slots), 6 * 4 * 3, "should have 72 slots (6×4×3)")

    def test_seventh_level_rejected(self):
        self._gen_rack("R-T2")
        rack = self.env["stock.location"].search([
            ("wms_rack_code", "=", "R-T2"),
        ], limit=1)
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create({
                "name": "L-7",
                "location_id": rack.id,
                "usage": "view",
                "wms_location_type": "level",
                "wms_level_number": 7,
                "company_id": rack.company_id.id,
            })

    def test_fourth_slot_rejected(self):
        self._gen_rack("R-T3")
        divider = self.env["stock.location"].search([
            ("wms_location_type", "=", "divider"),
        ], limit=1)
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create({
                "name": "S-4",
                "location_id": divider.id,
                "usage": "internal",
                "wms_location_type": "slot",
                "wms_slot_number": 4,
                "company_id": divider.company_id.id,
            })

    def test_divider_under_rack_rejected(self):
        """Dividers must sit under a Level, not directly under a Rack."""
        self._gen_rack("R-T4")
        rack = self.env["stock.location"].search([
            ("wms_rack_code", "=", "R-T4"),
        ], limit=1)
        with self.assertRaises(ValidationError):
            self.env["stock.location"].create({
                "name": "D-bad",
                "location_id": rack.id,
                "usage": "view",
                "wms_location_type": "divider",
                "company_id": rack.company_id.id,
            })

    def test_fifo_helper(self):
        self._gen_rack("R-FIFO", dividers_per_level=2)
        slots = self.env["stock.location"].search([
            ("wms_location_type", "=", "slot"),
            ("location_id.location_id.location_id.wms_rack_code", "=", "R-FIFO"),
        ], limit=3)
        self.assertEqual(len(slots), 3)
        product = self.env["product.product"].create({
            "name": "Demo Widget",
            "type": "product",
        })
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
        self.assertEqual(plan[0][0], q1)
        self.assertEqual(plan[0][1], 5.0)
        self.assertEqual(plan[1][0], q2)
        self.assertEqual(plan[1][1], 1.0)

"""Wave 2 Wave-2-3 — Department / Animal / Medicine usage reports.

Drive a real Scan Issue (so the issue-dimension fields and the frozen
``wms_unit_cost_at_done`` cost snapshot are stamped exactly as in production)
and assert the three SQL views aggregate the consumed qty / value correctly:

* department usage groups by department,
* animal usage counts only issues that named an animal,
* medicine consumption is restricted to the ``medicine`` kind and buckets by
  month.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestUsageReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "USAGE Keeper"})
        cls.dept = cls.env["wms.department"].create({"name": "USAGE Veterinary", "code": "USGVET"})
        cls.animal = cls.env["wms.animal"].create({"name": "USAGE Gauri", "tag": "USG-COW-1"})

        # A medicine product and a non-medicine product, both with cost + stock.
        cls.med = cls.env["product.product"].create(
            {
                "name": "USAGE Vaccine",
                "type": "consu",
                "is_storable": True,
                "barcode": "USAGEMED01",
                "wms_product_kind": "medicine",
            }
        )
        cls.med.standard_price = 20.0
        cls.feed = cls.env["product.product"].create(
            {
                "name": "USAGE Feed",
                "type": "consu",
                "is_storable": True,
                "barcode": "USAGEFEED1",
                "wms_product_kind": "feed",
            }
        )
        cls.feed.standard_price = 5.0
        # medicine/feed are auto lot-tracked (V20-003), so stock must carry a lot.
        # Far-dated (400d) to clear the V20-022 short-dated-at-issue guard.
        far = fields.Datetime.now() + timedelta(days=400)
        cls.med_lot = cls.env["stock.lot"].create(
            {
                "name": "USG-MED-LOT",
                "product_id": cls.med.id,
                "company_id": cls.env.company.id,
                "expiration_date": far,
            }
        )
        cls.feed_lot = cls.env["stock.lot"].create(
            {
                "name": "USG-FEED-LOT",
                "product_id": cls.feed.id,
                "company_id": cls.env.company.id,
                "expiration_date": far,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.med, cls.stock, 50.0, lot_id=cls.med_lot
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.feed, cls.stock, 50.0, lot_id=cls.feed_lot
        )
        cls.env.flush_all()

    def _issue(self, barcode, qty, animal=None):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": barcode,
                "taken_by": "Vet",
                "ordered_by": "Manager",
                "usage_note": "usage report test",
                "storekeeper_id": self.keeper.id,
                "department_id": self.dept.id,
                "animal_id": animal.id if animal else False,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "the issue should have created a picking")
        return wiz.picking_id

    def test_department_usage_value(self):
        # 3 vaccine x 20.0 + 4 feed x 5.0 = 60 + 20 = 80, all under USAGE Veterinary.
        self._issue("USAGEMED01", 3.0, animal=self.animal)
        self._issue("USAGEFEED1", 4.0)
        self.env.flush_all()
        rows = self.env["wms.department.usage"].search([("department_id", "=", self.dept.id)])
        self.assertTrue(rows, "the department should appear in the department-usage view")
        self.assertAlmostEqual(sum(rows.mapped("qty_out")), 7.0, places=2)
        self.assertAlmostEqual(sum(rows.mapped("usage_value")), 80.0, places=2)
        # month bucket truncated to the first of the month
        self.assertTrue(all(r.period.day == 1 for r in rows), "period must be month-truncated")

    def test_animal_usage_only_counts_named_animal(self):
        # One issue NAMES the animal (3 x 20.0 = 60), one does NOT (the feed).
        self._issue("USAGEMED01", 3.0, animal=self.animal)
        self._issue("USAGEFEED1", 4.0)  # no animal
        self.env.flush_all()
        rows = self.env["wms.animal.usage"].search([("animal_id", "=", self.animal.id)])
        self.assertTrue(rows, "the named animal should appear in the animal-usage view")
        self.assertAlmostEqual(sum(rows.mapped("qty_out")), 3.0, places=2)
        self.assertAlmostEqual(sum(rows.mapped("usage_value")), 60.0, places=2)
        # the feed issue carried no animal, so it must not appear anywhere here
        all_rows = self.env["wms.animal.usage"].search([("product_id", "=", self.feed.id)])
        self.assertFalse(
            all_rows, "an issue with no animal stamped must not appear in animal usage"
        )

    def test_medicine_consumption_excludes_non_medicine(self):
        self._issue("USAGEMED01", 3.0, animal=self.animal)
        self._issue("USAGEFEED1", 4.0)
        self.env.flush_all()
        med_rows = self.env["wms.medicine.consumption"].search([("product_id", "=", self.med.id)])
        self.assertTrue(med_rows, "the medicine should appear in the medicine-consumption view")
        self.assertAlmostEqual(sum(med_rows.mapped("qty_out")), 3.0, places=2)
        self.assertAlmostEqual(sum(med_rows.mapped("consumption_value")), 60.0, places=2)
        self.assertAlmostEqual(med_rows[0].unit_cost, 20.0, places=2)
        # the non-medicine feed must NOT appear in the medicine view
        feed_rows = self.env["wms.medicine.consumption"].search([("product_id", "=", self.feed.id)])
        self.assertFalse(
            feed_rows, "a non-medicine product must not appear in medicine consumption"
        )

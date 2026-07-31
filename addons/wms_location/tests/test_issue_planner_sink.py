# -*- coding: utf-8 -*-
"""UAT R4 — the issue planner must never plan out of the consumed-goods sink.

"Trust internal use" is where ISSUED goods are moved to: it is the ledger of
what has left the shelf, not stock. But it is usage='internal' exactly like a
rack, and the planner's fallback pass — which exists so a trust that parked its
racks outside WH/Stock still gets served — searched every internal location in
the company. So with an empty shelf it planned issues STRAIGHT OUT OF THE SINK:
the keeper scans, gets a plan, validates, and the system hands out goods that
were already handed out, while the sink balance never drains.

Reproduced on a copy of the live database before the fix: 0 on the shelf, 7 in
the sink, and the planner offered 5 of them.

These tests pin both halves — the sink is never a source, and the fallback that
the exclusion sits inside still works for genuinely out-of-tree storage.
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_planner_sink")
class TestIssuePlannerSink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.sink = cls.env.ref("wms_location.stock_location_trust_use")
        cls.Quant = cls.env["stock.quant"]
        cls.Planner = cls.env["stock.location"]

    def _product(self, name):
        return (
            self.env["product.template"]
            .create({"name": name, "wms_product_kind": "tool"})
            .product_variant_id
        )

    def test_01_sink_is_flagged(self):
        """The hook/migration must have stamped the sink, or nothing below
        can distinguish it from a shelf."""
        self.assertTrue(
            self.sink.wms_is_trust_use,
            "the consumed-goods sink must carry wms_is_trust_use",
        )

    def test_02_empty_shelf_plus_sink_balance_plans_nothing(self):
        """The exact live shape: everything issued out, nothing on the shelf."""
        product = self._product("SINK Already Issued")
        self.Quant._update_available_quantity(product, self.sink, 7)
        self.env.flush_all()

        plan, missing = self.Planner.find_oldest_quants_for_product(
            product.id, 5, parent_location_id=self.stock.id
        )

        self.assertFalse(plan, "consumed goods must never be offered for re-issue")
        self.assertEqual(
            missing, 5, "the keeper must be told it is out of stock, not handed a plan"
        )

    def test_03_sink_is_not_mixed_in_with_real_shelf_stock(self):
        """Shelf stock is issuable; the sink alongside it must be ignored."""
        product = self._product("SINK Mixed")
        slot = self.env["stock.location"].create(
            {
                "name": "SINK-TEST-ZONE",
                "usage": "internal",
                "location_id": self.stock.id,
                "wms_location_type": "zone",
            }
        )
        self.Quant._update_available_quantity(product, slot, 2)
        self.Quant._update_available_quantity(product, self.sink, 50)
        self.env.flush_all()

        plan, missing = self.Planner.find_oldest_quants_for_product(
            product.id, 10, parent_location_id=self.stock.id
        )

        self.assertTrue(plan, "the 2 real units on the shelf are issuable")
        self.assertEqual(
            sum(take for _q, take in plan), 2, "only the shelf's 2 units, never the sink's 50"
        )
        self.assertEqual(missing, 8, "the shortfall must be reported honestly")
        for quant, _take in plan:
            self.assertFalse(
                quant.location_id.wms_is_trust_use, "no plan line may come from the sink"
            )

    def test_04_out_of_tree_fallback_still_works(self):
        """The exclusion must not break the fallback it lives inside: real
        storage parked outside the warehouse tree (a database restored from an
        older backup) is still reachable."""
        product = self._product("SINK Fallback")
        outside = (
            self.env["stock.location"]
            .with_context(wms_skip_tree_check=True)
            .create(
                {
                    "name": "SINK Outside Area",
                    "usage": "internal",
                    "location_id": False,
                    "company_id": self.env.company.id,
                    "wms_location_type": "floor",
                }
            )
        )
        self.Quant._update_available_quantity(product, outside, 4)
        self.env.flush_all()

        plan, missing = self.Planner.find_oldest_quants_for_product(
            product.id, 3, parent_location_id=self.stock.id
        )

        self.assertTrue(plan, "genuinely stored stock outside the tree must still be found")
        self.assertEqual(missing, 0)
        self.assertEqual(plan[0][0].location_id, outside)

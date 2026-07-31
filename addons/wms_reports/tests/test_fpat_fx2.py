"""FPAT FX-2 regressions: report correctness fixes.

  * FEFO actually orders by wms_expiry_date for expiry-sensitive kinds.
  * /wms/find substring keyword router no longer hijacks product searches.
  * damage_value is a snapshot - editing quantity does NOT rewrite history.
  * Consumption Value reads the wms_unit_cost_at_done snapshot - changing
    standard_price after the fact does NOT rewrite past-month totals.
  * Expiry value-at-risk excludes the Trust-use sink and Damage / Repair.
"""

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx2")
class TestFpatFx2Fefo(TransactionCase):
    def test_fefo_sort_picks_sooner_expiring_first(self):
        """The shared removal sort must order EXPIRY_SENSITIVE_KINDS by
        wms_expiry_date asc, not by in_date asc. (FEFO, not FIFO.)"""
        wh = self.env["stock.warehouse"].search([], limit=1)
        floor_a = self.env["stock.location"].create(
            {
                "name": "FX2 FEFO A",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        floor_b = self.env["stock.location"].create(
            {
                "name": "FX2 FEFO B",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        # tmpl_a: older arrival (2026-01) but LATER expiry (2028).
        tmpl_a = self.env["product.template"].create(
            {
                "name": "FX2 Med A",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "wms_expiry_date": "2028-12-31",
            }
        )
        prod_a = tmpl_a.product_variant_id
        self.env["stock.quant"]._update_available_quantity(prod_a, floor_a, 10.0)
        self.env["stock.quant"].search(
            [("product_id", "=", prod_a.id), ("location_id", "=", floor_a.id)]
        ).write({"in_date": "2026-01-01 00:00:00"})
        # tmpl_b: newer arrival (2026-03) but SOONER expiry (2026-06).
        tmpl_b = self.env["product.template"].create(
            {
                "name": "FX2 Med B",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "wms_expiry_date": "2026-06-30",
            }
        )
        prod_b = tmpl_b.product_variant_id
        self.env["stock.quant"]._update_available_quantity(prod_b, floor_b, 10.0)
        self.env["stock.quant"].search(
            [("product_id", "=", prod_b.id), ("location_id", "=", floor_b.id)]
        ).write({"in_date": "2026-03-01 00:00:00"})

        quants = self.env["stock.quant"].search(
            [("product_id", "in", [prod_a.id, prod_b.id]), ("quantity", ">", 0)]
        )
        ordered = quants._wms_sorted_for_removal()
        self.assertEqual(
            ordered[0].product_id, prod_b, "sooner-expiring batch must come first under FEFO"
        )
        self.assertEqual(ordered[1].product_id, prod_a)


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx2")
class TestFpatFx2FindRouting(HttpCase):
    def test_slow_cooker_search_is_not_hijacked_to_dead_stock(self):
        self.env.ref("base.user_admin").write(
            {"group_ids": [(4, self.env.ref("wms_location.group_wms_user").id)]}
        )
        wh = self.env["stock.warehouse"].search([], limit=1)
        floor = self.env["stock.location"].create(
            {
                "name": "FX2 Find Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        prod = self.env["product.product"].create(
            {
                "name": "Slow Cooker 5L",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        self.env["stock.quant"]._update_available_quantity(prod, floor, 1.0)
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/find?q=Slow+Cooker")
        self.assertEqual(resp.status_code, 200)
        # The product card must appear; the dead-stock heading must NOT.
        self.assertIn("Slow Cooker 5L", resp.text)
        self.assertNotIn("Dead / slow stock", resp.text)


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx2")
class TestFpatFx2DamageValueSnapshot(TransactionCase):
    def test_damage_value_does_not_rewrite_when_cost_changes(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        floor = self.env["stock.location"].create(
            {
                "name": "FX2 DamSnap",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "FX2 Damage Snap",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        product.standard_price = 100.0
        self.env["stock.quant"]._update_available_quantity(product, floor, 10.0)
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "FX2 Keeper"})
        dmg = self.env["wms.damage"].create(
            {
                "product_id": product.id,
                "quantity": 5.0,
                "source_slot_id": floor.id,
                "reason": "broken",
                "wms_reported_by": "X",
                "wms_authorized_by": "Y",
                "wms_storekeeper_id": keeper.id,
            }
        )
        dmg.action_confirm()
        self.assertAlmostEqual(dmg.damage_value, 500.0, places=2)
        # Now change the cost, then "re-save" the damage record.
        product.standard_price = 120.0
        dmg.write({"note": "audited"})
        # value must remain frozen at 500, NOT recompute to 600.
        self.assertAlmostEqual(
            dmg.damage_value, 500.0, places=2, msg="damage_value must be a snapshot"
        )

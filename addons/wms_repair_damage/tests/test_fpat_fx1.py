"""FPAT FX-1 regression: critical/high crashes the FPAT audit surfaced. Each
test reproduces the exact scenario the auditor recorded and confirms the fix.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_fpat_fx1")
class TestFpatFx1Damage(TransactionCase):
    """C: wms.damage.action_confirm() crashed with TypeError on every success
    path because rec.product_id._fields['wms_product_kind'].selection was a
    lambda for related Selections. Now reads the static list from the template.
    """

    def test_action_confirm_does_not_crash_on_kind_label(self):
        wh = self.env["stock.warehouse"].search([], limit=1)
        floor = self.env["stock.location"].create(
            {
                "name": "FX1 Damage Floor",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "floor",
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "FX1 Damage Probe",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "consumable",
            }
        )
        self.env["stock.quant"]._update_available_quantity(product, floor, 10.0)
        keeper = self.env["wms.storekeeper"].search([], limit=1) or self.env[
            "wms.storekeeper"
        ].create({"name": "FX1 Keeper"})
        dmg = self.env["wms.damage"].create(
            {
                "product_id": product.id,
                "quantity": 2.0,
                "source_slot_id": floor.id,
                "reason": "broken",
                "wms_reported_by": "Test reporter",
                "wms_authorized_by": "Test authoriser",
                "wms_storekeeper_id": keeper.id,
            }
        )
        # The auditor's repro: this was raising
        # TypeError: 'function' object is not iterable. Must complete cleanly.
        dmg.action_confirm()
        self.assertEqual(dmg.state, "confirmed")
        self.assertTrue(dmg.recommended_action, "recommended_action must be set")
        self.assertTrue(dmg.recommendation_message, "the message must include the kind label")

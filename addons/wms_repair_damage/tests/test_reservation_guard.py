"""High - damage/repair confirmation must ABORT (not force a phantom deduction)
when the source stock vanished between filing and confirmation - the TOCTOU race
a concurrent Scan Issue opens. ``validate_reserved_or_abort`` locks the product
and refuses to validate a move that could not be reserved, so on-hand can never
be driven negative.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_reservation_guard")
class TestReservationGuard(TransactionCase):
    def test_damage_confirm_aborts_when_stock_vanished(self):
        product = self.env["product.product"].create({"name": "Guard Product", "is_storable": True})
        slot = self.env.ref("stock.stock_location_stock")
        keeper = self.env["wms.storekeeper"].create({"name": "Guard Keeper"})
        # 5 present -> a damage of 5 is creatable (passes the source-stock check).
        self.env["stock.quant"]._update_available_quantity(product, slot, 5.0)
        dmg = self.env["wms.damage"].create(
            {
                "product_id": product.id,
                "source_slot_id": slot.id,
                "quantity": 5.0,
                "wms_reported_by": "Tester",
                "wms_authorized_by": "Supervisor",
                "wms_storekeeper_id": keeper.id,
            }
        )
        # A concurrent Scan Issue drains the slot between filing and confirm.
        self.env["stock.quant"]._update_available_quantity(product, slot, -5.0)

        with self.assertRaises(UserError):
            dmg.action_confirm()

        # Aborted cleanly: not posted, and on-hand was not driven negative.
        self.assertNotEqual(dmg.state, "confirmed")
        on_hand = sum(
            self.env["stock.quant"]
            .search([("product_id", "=", product.id), ("location_id", "=", slot.id)])
            .mapped("quantity")
        )
        self.assertGreaterEqual(on_hand, 0.0)

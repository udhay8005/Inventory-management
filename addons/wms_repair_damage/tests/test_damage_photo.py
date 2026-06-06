"""Maturity: a first-class damage-evidence photo field on wms.damage (opens the
camera on a phone/tablet via widget=image), so damage proof is captured in a
guided field instead of only as a loose chatter attachment."""

import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_damage_photo")
class TestDamagePhoto(TransactionCase):
    def test_damage_photo_field_stores(self):
        self.assertIn("damage_photo", self.env["wms.damage"]._fields)
        product = self.env["product.product"].create({"name": "Photo Dmg", "is_storable": True})
        slot = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(product, slot, 1.0)
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n")
        dmg = self.env["wms.damage"].create(
            {
                "product_id": product.id,
                "source_slot_id": slot.id,
                "quantity": 1.0,
                "damage_photo": png,
            }
        )
        self.assertTrue(dmg.damage_photo, "damage photo should be stored")

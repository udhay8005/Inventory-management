"""Wave 2 #11 — status-aware heat map: status colour overrides occupancy."""

from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestHeatmap(HttpCase):
    def test_heatmap_shows_recall_status_colour(self):
        env = self.env
        wh = env["stock.warehouse"].search([], limit=1)
        zone = env["stock.location"].create(
            {
                "name": "HM Zone",
                "usage": "internal",
                "location_id": wh.lot_stock_id.id,
                "wms_location_type": "zone",
            }
        )
        floor = env["stock.location"].create(
            {
                "name": "HM Floor",
                "usage": "internal",
                "location_id": zone.id,
                "wms_location_type": "floor",
            }
        )
        med = env["product.product"].create(
            {
                "name": "HM Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "HMMED01",
            }
        )
        lot = env["stock.lot"].create(
            {
                "name": "HM-LOT",
                "product_id": med.id,
                "company_id": env.company.id,
                "expiration_date": fields.Datetime.now() + timedelta(days=400),
                "wms_lot_state": "recalled",
            }
        )
        env["stock.quant"]._update_available_quantity(med, floor, 10, lot_id=lot)
        env.flush_all()

        env["res.users"].create(
            {
                "name": "HM User",
                "login": "hm_user",
                "password": "hm_user",
                "group_ids": [(4, env.ref("wms_location.group_wms_user").id)],
            }
        )
        self.authenticate("hm_user", "hm_user")
        r = self.url_open("/wms/intelligence/heatmap")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Warehouse Heat Map", body)
        self.assertIn("HM Floor", body)
        # The recall status colour (precedence over occupancy) must be applied.
        self.assertIn("#7f1d1d", body, "a floor holding a recalled lot must show the recall colour")

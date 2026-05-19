import logging
import random
from datetime import datetime, timedelta

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Five realistic warehouse products. Each gets a unique unit barcode + a
# carton barcode alias if it's a bulk item. Stock is sprinkled across
# random slots with mixed in_dates so FIFO has something to chew on.
DEMO_PRODUCTS = [
    # (name, default_code, unit_barcode, list_price, is_bulk, carton_qty, carton_barcode)
    # All are storable so stock.quant can hold them; `is_bulk` only drives
    # whether we seed a carton barcode + larger qty.
    ("Screw M4×20mm", "SCRW-M4-20", "8901111000001", 0.05, True, 1000, "CTN-SCRW-M4-20-1000"),
    ("Hex Nut M4", "NUT-M4", "8901111000002", 0.03, True, 500, "CTN-NUT-M4-500"),
    ("Cable Tie 200mm", "TIE-200", "8901111000003", 0.12, True, 100, "CTN-TIE-200-100"),
    ("Power Drill 18V", "DRILL-18V", "8901111000004", 4500, False, 0, None),
    ("Safety Helmet", "HELMET-01", "8901111000005", 320, False, 0, None),
]


class WmsDemoSeeder(models.TransientModel):
    """Click-to-seed demo products + stock distribution across the slots
    of an existing rack. Idempotent on barcode: re-running won't duplicate
    products, only top up stock if `add_stock` is set.
    """

    _name = "wms.demo.seeder"
    _description = "Seed demo products, barcodes and stock"

    rack_id = fields.Many2one(
        "stock.location",
        domain=[("wms_location_type", "=", "rack")],
        required=True,
        default=lambda self: self.env["stock.location"].search(
            [("wms_location_type", "=", "rack")],
            limit=1,
        ),
    )
    add_stock = fields.Boolean(
        default=True,
        help="Also distribute some initial stock across the rack's slots.",
    )

    def action_seed(self):
        self.ensure_one()
        if not self.rack_id:
            raise UserError("No rack selected. Generate one first.")

        Product = self.env["product.product"]
        Alias = self.env["wms.barcode.alias"]
        Quant = self.env["stock.quant"]

        slots = self.env["stock.location"].search(
            [
                ("id", "child_of", self.rack_id.id),
                ("wms_location_type", "=", "slot"),
            ]
        )
        if not slots:
            raise UserError("Rack %s has no slots." % self.rack_id.display_name)

        created_products = 0
        created_quants = 0

        for name, code, barcode, price, is_bulk, ctn_qty, ctn_barcode in DEMO_PRODUCTS:
            product = Product.search([("barcode", "=", barcode)], limit=1)
            if not product:
                product = Product.create(
                    {
                        "name": name,
                        "default_code": code,
                        "barcode": barcode,
                        "list_price": price,
                        # Odoo 19: storable = consu + is_storable
                        "type": "consu",
                        "is_storable": True,
                    }
                )
                created_products += 1

            if ctn_barcode and not Alias.search([("barcode", "=", ctn_barcode)], limit=1):
                Alias.create(
                    {
                        "barcode": ctn_barcode,
                        "product_id": product.id,
                        "units_per_scan": ctn_qty,
                        "note": "Auto-seeded carton barcode for %s" % name,
                    }
                )

            if not self.add_stock:
                continue

            # Spread 2-3 quants per product across random slots with
            # different in_dates so FIFO has something to demonstrate.
            chosen = random.sample(list(slots), min(3, len(slots)))
            base_date = datetime.utcnow() - timedelta(days=random.randint(5, 60))
            for i, slot in enumerate(chosen):
                qty = float(random.randint(20, 400)) if is_bulk else float(random.randint(1, 5))
                Quant.create(
                    {
                        "product_id": product.id,
                        "location_id": slot.id,
                        "quantity": qty,
                        "in_date": base_date + timedelta(days=i * 3),
                    }
                )
                created_quants += 1

        _logger.info("wms_demo_seeder: %d products, %d quants", created_products, created_quants)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Demo data seeded",
                "message": (
                    "Created %d products and distributed stock across %d slot(s) in rack %s. "
                    "Open Scan Receipt or Scan Issue to try it out."
                )
                % (created_products, created_quants, self.rack_id.display_name),
                "sticky": False,
            },
        }

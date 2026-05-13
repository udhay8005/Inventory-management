from odoo import api, fields, models


class WmsBarcodeAlias(models.Model):
    """Many physical barcodes → one product.

    Used so a vendor carton sticker like 'CTN-COKE-24' resolves to product
    'Coke 350ml' with units_per_scan=24. The unit barcode on
    product.product.barcode is still respected.
    """
    _name = "wms.barcode.alias"
    _description = "Carton/box barcode alias"
    _rec_name = "barcode"

    barcode = fields.Char(required=True, index=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade")
    units_per_scan = fields.Float(default=1.0, required=True,
                                  help="How many product units one scan of this barcode represents.")
    note = fields.Char()

    _sql_constraints = [
        ("barcode_unique", "UNIQUE(barcode)", "Each carton barcode must be unique."),
    ]

    @api.model
    def resolve(self, barcode):
        """Return (product, units_per_scan) for an arbitrary scanned string.

        Search order:
          1. product.product.barcode (unit)
          2. wms.barcode.alias (carton)
          3. stock.lot.name (existing lot)
          4. stock.location.barcode (a slot / rack)
        Returns dict with key 'kind' in {'product','alias','lot','location',None}.
        """
        if not barcode:
            return {"kind": None}
        barcode = barcode.strip()

        product = self.env["product.product"].search(
            [("barcode", "=", barcode)], limit=1
        )
        if product:
            return {"kind": "product", "product": product, "units": 1.0}

        alias = self.search([("barcode", "=", barcode)], limit=1)
        if alias:
            return {"kind": "alias", "product": alias.product_id,
                    "units": alias.units_per_scan, "alias": alias}

        lot = self.env["stock.lot"].search([("name", "=", barcode)], limit=1)
        if lot:
            return {"kind": "lot", "lot": lot, "product": lot.product_id, "units": 1.0}

        loc = self.env["stock.location"].search(
            [("barcode", "=", barcode)], limit=1
        )
        if loc:
            return {"kind": "location", "location": loc}

        return {"kind": None}

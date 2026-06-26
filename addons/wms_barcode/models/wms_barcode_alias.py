from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    units_per_scan = fields.Float(
        default=1.0,
        required=True,
        help="How many product units one scan of this barcode represents.",
    )
    note = fields.Char()

    _barcode_unique = models.Constraint(
        "UNIQUE(barcode)",
        "Each carton barcode must be unique.",
    )
    _units_per_scan_positive = models.Constraint(
        "CHECK(units_per_scan > 0)",
        "Units per scan must be greater than zero.",
    )

    @api.constrains("barcode")
    def _check_barcode_no_collision(self):
        """Critical #4: a carton alias barcode must not collide with a product
        barcode, a location barcode, or a lot/serial name.

        resolve() searches product -> alias -> lot -> location, so an alias
        that duplicates a product barcode is silently shadowed (its unit
        multiplier dropped) and one duplicating a slot barcode mis-routes the
        scan. Reject the collision up front.
        """
        coded = self.filtered("barcode")
        if not coded:
            return
        # Format-validate each alias barcode (reuses the product EAN-13 check),
        # so a carton EAN typed off a vendor box with a bad check digit is caught.
        Template = self.env["product.template"]
        for rec in coded:
            Template._wms_validate_barcode(rec.barcode)
        barcodes = coded.mapped("barcode")
        prod = self.env["product.product"].search([("barcode", "in", barcodes)], limit=1)
        if prod:
            raise ValidationError(
                _("Barcode %s is already a product's unit barcode.") % prod.barcode
            )
        loc = self.env["stock.location"].search([("barcode", "in", barcodes)], limit=1)
        if loc:
            raise ValidationError(_("Barcode %s is already a location barcode.") % loc.barcode)
        lot = self.env["stock.lot"].search([("name", "in", barcodes)], limit=1)
        if lot:
            raise ValidationError(_("Barcode %s is already a lot / serial number.") % lot.name)

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

        product = self.env["product.product"].search([("barcode", "=", barcode)], limit=1)
        if product:
            return {"kind": "product", "product": product, "units": 1.0}

        alias = self.search([("barcode", "=", barcode)], limit=1)
        if alias:
            return {
                "kind": "alias",
                "product": alias.product_id,
                "units": alias.units_per_scan,
                "alias": alias,
            }

        lot = self.env["stock.lot"].search([("name", "=", barcode)], limit=1)
        if lot:
            return {"kind": "lot", "lot": lot, "product": lot.product_id, "units": 1.0}

        loc = self.env["stock.location"].search([("barcode", "=", barcode)], limit=1)
        if loc:
            return {"kind": "location", "location": loc}

        return {"kind": None}

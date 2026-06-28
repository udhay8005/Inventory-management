# File: models/wms_pharma_packaging_barcode.py
# Module: wms_pharmacy
# Description: Nested packaging barcode model (wms.pharma.packaging.barcode).
#              Each row maps one physical barcode (box, strip, or tablet label)
#              to a product and computes how many base tablet-units that scan
#              represents. The resolve() class method is the public API called
#              by the dispense wizard and any future barcode scanner integration.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: product.product, stock.lot, stock.location

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsPharmaPakagingBarcode(models.Model):
    """Pharmacy nested packaging barcode.

    Represents one physical barcode label printed on a box, strip, or tablet
    blister of a packaged medicine. Scanning such a barcode via ``resolve()``
    returns the product and the number of base tablet-units the scan represents.

    The uniqueness constraint prevents the same barcode string being registered
    at different tiers. The ``_check_no_collision`` constrains prevents shadowing
    an existing product/location/lot barcode.

    Usage example::

        # Register a box barcode for Oxy 500mg (50 tablets per box)
        env['wms.pharma.packaging.barcode'].create({
            'product_id': oxy.id,
            'tier': 'box',
            'barcode': 'PHB-OXY-BOX-001',
        })
        result = env['wms.pharma.packaging.barcode'].resolve('PHB-OXY-BOX-001')
        # result == {'kind': 'pharma', 'product': oxy, 'tier': 'box', 'base_units': 50}
    """

    _name = "wms.pharma.packaging.barcode"
    _description = "Pharmacy packaging barcode (box / strip / tablet)"
    _rec_name = "barcode"
    _order = "product_id, tier"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
        ondelete="cascade",
        domain="[('product_tmpl_id.wms_is_packaged', '=', True)]",
        help="The packaged medicine this barcode belongs to.",
    )
    tier = fields.Selection(
        [
            ("box", "Box (sealed full box)"),
            ("strip", "Strip (one sealed strip)"),
            ("tablet", "Tablet (individual tablet)"),
        ],
        string="Tier",
        required=True,
        index=True,
        help="Which packaging level this barcode label is printed on.",
    )
    barcode = fields.Char(
        string="Barcode",
        required=True,
        index=True,
        help="The scanned barcode string. Must be unique across all pharmacy "
        "packaging barcodes and must not collide with an existing product, "
        "location, or lot barcode.",
    )
    base_units = fields.Integer(
        string="Base units (tablets)",
        compute="_compute_base_units",
        store=True,
        readonly=True,
        help="How many individual tablets one scan of this barcode represents: "
        "box → tablets_per_box, strip → tablets_per_strip, tablet → 1.",
    )

    # ------------------------------------------------------------------
    # SQL constraints (Odoo 19 declarative style)
    # ------------------------------------------------------------------

    _barcode_unique = models.Constraint(
        "UNIQUE(barcode)",
        "Each pharmacy packaging barcode must be unique.",
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends(
        "tier",
        "product_id",
        "product_id.product_tmpl_id.wms_tablets_per_strip",
        "product_id.product_tmpl_id.wms_strips_per_box",
        "product_id.product_tmpl_id.wms_tablets_per_box",
    )
    def _compute_base_units(self):
        """Return the tablet count one scan of this barcode represents.

        :returns: Integer stored field.

        * box → ``product.wms_tablets_per_box``
        * strip → ``product.wms_tablets_per_strip``
        * tablet → 1
        """
        for rec in self:
            tmpl = rec.product_id.product_tmpl_id
            if rec.tier == "box":
                rec.base_units = tmpl.wms_tablets_per_box or 0
            elif rec.tier == "strip":
                rec.base_units = tmpl.wms_tablets_per_strip or 0
            elif rec.tier == "tablet":
                rec.base_units = 1
            else:
                rec.base_units = 0

    # ------------------------------------------------------------------
    # Python constraints
    # ------------------------------------------------------------------

    @api.constrains("barcode")
    def _check_no_collision(self):
        """Reject barcodes that collide with product, location, or lot codes.

        Mirrors the collision guard in ``wms.barcode.alias._check_barcode_no_collision``
        (best-effort: checks the three main namespaces that the existing
        resolve() search order visits).

        :raises ValidationError: on any detected collision.
        """
        for rec in self.filtered("barcode"):
            bc = rec.barcode
            product = self.env["product.product"].search([("barcode", "=", bc)], limit=1)
            if product:
                raise ValidationError(_("Barcode '%s' is already a product's unit barcode.") % bc)
            loc = self.env["stock.location"].search([("barcode", "=", bc)], limit=1)
            if loc:
                raise ValidationError(_("Barcode '%s' is already a location barcode.") % bc)
            lot = self.env["stock.lot"].search([("name", "=", bc)], limit=1)
            if lot:
                raise ValidationError(_("Barcode '%s' is already a lot / serial number.") % bc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def resolve(self, barcode):
        """Resolve a scanned barcode string to pharmacy packaging metadata.

        Search order (fast path first):
        1. Look up ``wms.pharma.packaging.barcode`` by barcode string.
        2. If found, return ``kind='pharma'`` with product, tier, base_units.
        3. If not found, return ``kind=None`` so the caller falls through to
           the standard ``wms.barcode.alias.resolve()`` chain.

        :param barcode: str — the raw scanned string.
        :returns: dict — ``{'kind': 'pharma', 'product': ..., 'tier': ...,
                   'base_units': ...}`` or ``{'kind': None}``.
        """
        if not barcode:
            return {"kind": None}
        barcode = barcode.strip()
        if not barcode:
            return {"kind": None}
        rec = self.search([("barcode", "=", barcode)], limit=1)
        if not rec:
            return {"kind": None}
        return {
            "kind": "pharma",
            "product": rec.product_id,
            "tier": rec.tier,
            "base_units": rec.base_units,
        }

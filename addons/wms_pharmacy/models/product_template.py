# File: models/product_template.py
# Module: wms_pharmacy
# Description: Extends product.template with Box→Strip→Tablet packaging hierarchy.
#              Adds wms_is_packaged flag, strip/box counts, and a computed
#              tablets_per_box field. A Python constraint enforces that packaged
#              products carry positive strip and box counts.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: wms_location (product.template), wms_perishable

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    """Pharmacy packaging hierarchy extension on product.template.

    When ``wms_is_packaged`` is True the product is dispensed in the
    Box > Strip > Tablet hierarchy. The two integer counts let the dispense
    engine compute how many tablets a sealed box contains and how many are
    left in an open strip.

    Usage example::

        tmpl = env['product.template'].create({
            'name': 'Oxytetracycline 500mg',
            'wms_product_kind': 'medicine',
            'wms_is_packaged': True,
            'wms_tablets_per_strip': 10,
            'wms_strips_per_box': 5,
        })
        # tmpl.wms_tablets_per_box == 50
    """

    _inherit = "product.template"

    # ------------------------------------------------------------------
    # Packaging hierarchy fields
    # ------------------------------------------------------------------

    wms_is_packaged = fields.Boolean(
        string="Packaged (Box→Strip→Tablet)",
        default=False,
        tracking=True,
        help="Tick when this medicine is dispensed as sealed boxes of strips "
        "of tablets. Enables the pharmacy packaging counts below and the "
        "FEFO open-strip dispense wizard.",
    )
    wms_tablets_per_strip = fields.Integer(
        string="Tablets per strip",
        default=0,
        tracking=True,
        help="Number of tablets in one sealed strip. Required when "
        "'Packaged' is ticked (must be > 0).",
    )
    wms_strips_per_box = fields.Integer(
        string="Strips per box",
        default=0,
        tracking=True,
        help="Number of strips in one sealed box. Required when "
        "'Packaged' is ticked (must be > 0).",
    )
    wms_tablets_per_box = fields.Integer(
        string="Tablets per box",
        compute="_compute_wms_tablets_per_box",
        store=True,
        readonly=True,
        help="Computed: tablets_per_strip × strips_per_box. The total "
        "number of tablets in one sealed box; used by the dispense engine "
        "to convert stock (boxes) to tablet quantities.",
    )

    @api.depends("wms_tablets_per_strip", "wms_strips_per_box")
    def _compute_wms_tablets_per_box(self):
        """Multiply strip and box counts to get the box tablet capacity.

        :returns: stored Integer; 0 when either factor is 0 or negative.
        """
        for tmpl in self:
            ts = tmpl.wms_tablets_per_strip or 0
            sb = tmpl.wms_strips_per_box or 0
            tmpl.wms_tablets_per_box = ts * sb if (ts > 0 and sb > 0) else 0

    @api.constrains("wms_is_packaged", "wms_tablets_per_strip", "wms_strips_per_box")
    def _check_wms_packaging_counts(self):
        """When packaged, both per-strip and per-box counts must be positive.

        :raises ValidationError: if wms_is_packaged is True but either count
            is zero or negative.
        """
        for tmpl in self:
            if not tmpl.wms_is_packaged:
                continue
            if tmpl.wms_tablets_per_strip <= 0 or tmpl.wms_strips_per_box <= 0:
                raise ValidationError(
                    _(
                        "Product '%(name)s' is marked as packaged "
                        "(Box→Strip→Tablet) but has invalid counts.\n\n"
                        "Both 'Tablets per strip' and 'Strips per box' must be "
                        "greater than zero. Please fill them in before saving."
                    )
                    % {"name": tmpl.display_name}
                )

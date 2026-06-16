"""product.category extension: editable enterprise tree + per-category
required-identity matrix + a one-way bridge to the WMS kind.

The owner's Product-Master design (docs/PRODUCT-MASTER-BUILD-SPEC.md)
makes the native product.category tree the admin-editable enterprise
hierarchy (Animal Care ▸ Medicines, Feed ▸ Concentrate, Tools ▸ Power,
…). Two things are layered on top:

* ``active`` — Odoo 19 CE's product.category has NO active field, so the
  admin cannot "disable" a category without code. We add one; archived
  categories drop out of the pickers automatically.
* the per-category REQUIRED-identity matrix (which of Brand / Form /
  Strength / Size / Pack a new product must carry). These flags are
  defined here so the seeded tree can carry them, but they are INERT
  until P3 wires the enforcement; the ``wms_effective_req_*`` computes OR
  each flag down the parent chain so a sub-category inherits its branch's
  policy.

``wms_default_kind`` is a ONE-WAY bridge: picking a category pre-selects
the WMS kind in the creation wizard. ``wms_product_kind`` on the template
stays the authoritative driver of the SKU prefix / UoM / lifecycle — this
only suggests it.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .product_template import WMS_KIND_SELECTION


class ProductCategory(models.Model):
    _inherit = "product.category"

    active = fields.Boolean(
        default=True,
        help="Untick to disable (archive) this category — it stops appearing "
        "in the pickers. Existing products keep their category; nothing is "
        "deleted.",
    )

    wms_default_kind = fields.Selection(
        WMS_KIND_SELECTION,
        string="Default WMS kind",
        help="Picking this category pre-selects the WMS Kind for a new product "
        "(the Kind still drives the SKU prefix, unit and lifecycle).",
    )

    # Owner's per-category required-identity matrix. INERT until P3 wires
    # enforcement; carried here so the tree seed can set sensible defaults
    # the admin then tunes.
    wms_req_brand = fields.Boolean(string="Brand required", default=False)
    wms_req_form = fields.Boolean(string="Form required", default=False)
    wms_req_strength = fields.Boolean(string="Strength required", default=False)
    wms_req_size = fields.Boolean(string="Size required", default=False)
    wms_req_pack = fields.Boolean(string="Pack required", default=False)

    wms_form_is_model = fields.Boolean(
        string="Show 'Form' as 'Model'",
        default=False,
        help="For Tools / Spare Parts: label the Form field as 'Model' "
        "(e.g. Drill 12V / 18V) in the creation wizard.",
    )

    # Effective requiredness = own flag OR any ancestor's, so sub-categories
    # inherit a branch's policy. Stored + recursive, mirroring the native
    # _compute_complete_name pattern; cycle protection is provided by the
    # native _check_category_recursion guard.
    wms_effective_req_brand = fields.Boolean(
        compute="_compute_wms_effective_req", store=True, recursive=True
    )
    wms_effective_req_form = fields.Boolean(
        compute="_compute_wms_effective_req", store=True, recursive=True
    )
    wms_effective_req_strength = fields.Boolean(
        compute="_compute_wms_effective_req", store=True, recursive=True
    )
    wms_effective_req_size = fields.Boolean(
        compute="_compute_wms_effective_req", store=True, recursive=True
    )
    wms_effective_req_pack = fields.Boolean(
        compute="_compute_wms_effective_req", store=True, recursive=True
    )

    @api.depends(
        "parent_id",
        "wms_req_brand",
        "wms_req_form",
        "wms_req_strength",
        "wms_req_size",
        "wms_req_pack",
        "parent_id.wms_effective_req_brand",
        "parent_id.wms_effective_req_form",
        "parent_id.wms_effective_req_strength",
        "parent_id.wms_effective_req_size",
        "parent_id.wms_effective_req_pack",
    )
    def _compute_wms_effective_req(self):
        for categ in self:
            parent = categ.parent_id
            categ.wms_effective_req_brand = categ.wms_req_brand or bool(
                parent and parent.wms_effective_req_brand
            )
            categ.wms_effective_req_form = categ.wms_req_form or bool(
                parent and parent.wms_effective_req_form
            )
            categ.wms_effective_req_strength = categ.wms_req_strength or bool(
                parent and parent.wms_effective_req_strength
            )
            categ.wms_effective_req_size = categ.wms_req_size or bool(
                parent and parent.wms_effective_req_size
            )
            categ.wms_effective_req_pack = categ.wms_req_pack or bool(
                parent and parent.wms_effective_req_pack
            )

    # ---- Master-data governance: no near-duplicate categories ------------
    @staticmethod
    def _wms_norm_name(name):
        return " ".join(name.split()) if name else name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = self._wms_norm_name(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = self._wms_norm_name(vals["name"])
        return super().write(vals)

    @api.constrains("name", "parent_id")
    def _check_wms_category_name_unique(self):
        """Block case-/whitespace-only duplicate category names UNDER THE SAME
        parent (a 'Cleaning' under both Consumables and Chemicals is legitimate,
        but two 'Cleaning' under Consumables is garbage). Archive-inclusive."""
        for cat in self:
            name = (cat.name or "").strip()
            if not name:
                continue
            dup = self.with_context(active_test=False).search(
                [
                    ("id", "!=", cat.id),
                    ("parent_id", "=", cat.parent_id.id),
                    ("name", "=ilike", name),
                ],
                limit=1,
            )
            if dup:
                raise ValidationError(
                    _(
                        "A category named “%s” already exists under the same parent. "
                        "Rename it or reuse the existing one."
                    )
                    % name
                )

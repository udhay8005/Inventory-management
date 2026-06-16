"""Product-identity master registers: Family / Brand / Form.

The enterprise Product-Master model (see docs/PRODUCT-MASTER-BUILD-SPEC.md)
identifies a stockable item by Category -> Family -> Brand -> Variant ->
Form -> Strength -> Pack Size -> Unit. Family, Brand and Form are small
admin-editable MASTER registers (this file); Variant / Strength / Pack are
free text on the product; Category is the native product.category tree.

Each register row carries a human ``name`` plus a stable, unique,
UPPERCASE short ``code``. That code is the drift-proof abbreviation the
structured-SKU builder (P2) and the assisted-migration parser (P4) look up
deterministically -- set "Cipla" -> CIP once here, and every SKU/parse
reuses it, so abbreviations can never drift. Rows are archived
(``active=False``), never deleted, so historical products keep resolving.

Mirrors the wms.department register pattern (name + unique code + sequence
+ active). The shared shape lives on an abstract base so a future change is
made once; the UNIQUE(code) constraint is declared per concrete model so it
lands on each register's own table regardless of inheritance nuances.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WmsCodedMaster(models.AbstractModel):
    """Abstract base for the coded identity registers (Family/Brand/Form)."""

    _name = "wms.coded.master"
    _description = "WMS coded identity master (abstract base)"
    _order = "sequence, name"

    # Concrete models override the code length cap (Family/Brand 6, Form 4).
    _code_max_len = 6

    name = fields.Char(required=True, translate=True, index=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Stable UPPERCASE short code used as a SKU segment (e.g. PARA, "
        "CIP, TAB). Set it once: do not change it after products use it, or "
        "new SKUs would diverge from old ones.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.constrains("code")
    def _check_code(self):
        for rec in self:
            code = (rec.code or "").strip()
            if not code:
                continue
            if len(code) > rec._code_max_len:
                raise ValidationError(
                    _("Code %(code)r is too long — keep it to %(n)d characters or fewer.")
                    % {"code": code, "n": rec._code_max_len}
                )
            if not code.isalnum():
                raise ValidationError(
                    _("Code %r may use letters and digits only (no spaces or symbols).") % code
                )

    @api.constrains("name")
    def _check_name_unique_ci(self):
        """Master-data governance: block case-/whitespace-only duplicate names
        (e.g. 'Paracetamol' vs 'PARACETAMOL' vs 'Paracetamol  '). Names are
        normalized on write (whitespace collapsed) and compared case-insensitively
        across active AND archived rows, so the catalogue — and the SKUs composed
        from these masters — never fork on a near-duplicate. (Typos like 'Bosch'
        vs 'Bosche' are different strings; the autocomplete dropdown is the guard
        against those.)"""
        for rec in self:
            name = (rec.name or "").strip()
            if not name:
                continue
            dup = self.with_context(active_test=False).search(
                [("id", "!=", rec.id), ("name", "=ilike", name)], limit=1
            )
            if dup:
                raise ValidationError(
                    _(
                        "“%(name)s” already exists (code %(code)s). Pick the existing "
                        "entry instead of creating a near-duplicate — duplicates that "
                        "differ only in spelling or capitalisation corrupt the "
                        "catalogue and the SKUs built from it."
                    )
                    % {"name": dup.name, "code": dup.code or "—"}
                )

    @staticmethod
    def _wms_norm_name(name):
        """Collapse leading/trailing/internal whitespace so ' Cattle  Feed ' and
        'Cattle Feed' can't coexist as two masters."""
        return " ".join(name.split()) if name else name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
            if vals.get("name"):
                vals["name"] = self._wms_norm_name(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        if vals.get("name"):
            vals["name"] = self._wms_norm_name(vals["name"])
        return super().write(vals)


class WmsFamily(models.Model):
    _name = "wms.family"
    _inherit = "wms.coded.master"
    _description = "Product family / generic group"

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "This family code is already used — each code must be unique.",
    )


class WmsBrand(models.Model):
    _name = "wms.brand"
    _inherit = "wms.coded.master"
    _description = "Product brand / manufacturer"

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "This brand code is already used — each code must be unique.",
    )


class WmsForm(models.Model):
    _name = "wms.form"
    _inherit = "wms.coded.master"
    _description = "Product form (tablet / syrup / pellet …) or model"

    _code_max_len = 4

    default_uom_id = fields.Many2one(
        "uom.uom",
        string="Suggested unit",
        help="When this form is chosen for a NEW product, suggest this unit of "
        "measure (tablet → Units, syrup → L, powder → kg). It only seeds a new "
        "product's unit; it never changes the unit once stock exists.",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "This form code is already used — each code must be unique.",
    )

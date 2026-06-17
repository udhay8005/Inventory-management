"""P3 — Guided Product Creation wizard.

A focused, full-page form that walks an admin through creating ONE fully
classified product: Category → Kind → Family → Brand → Form → Strength → Pack,
with a LIVE SKU + barcode preview, a duplicate warning, category-driven required
fields, and inline creation of Family/Brand/Form — without leaving the screen.

It is a thin front-end over the proven engine: ``product.template.create()``
(wms_location) still does all the work — composes the structured Business SKU,
stamps the immutable PRD code, mints the Code128 + EAN-13, and BLOCKS a duplicate
identity. The wizard only gathers the fields, previews the result, and calls
create(). Required-field enforcement lives HERE (in the guided path) rather than
as a global model constraint, so the bulk Onboard / CSV import / plain product
form — which legitimately create kind-only products — are never broken.
"""

from odoo import _, api, fields, models
from odoo.addons.wms_location.models.product_template import (
    _KIND_DEFAULT_UOM_FALLBACK,
    KIND_DEFAULT_UOM,
    WMS_KIND_SELECTION,
)
from odoo.exceptions import UserError


class WmsProductCreate(models.TransientModel):
    _name = "wms.product.create"
    _description = "Guided product creation"

    # ---- classification -------------------------------------------------
    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        required=True,
        help="Pick where this product belongs. The category sets the WMS Kind "
        "and which identity fields are required.",
    )
    wms_product_kind = fields.Selection(
        WMS_KIND_SELECTION,
        string="WMS Kind",
        compute="_compute_kind",
        help="Derived from the category — drives the SKU prefix, the unit and "
        "the returnable/expiry rules.",
    )

    # ---- identity -------------------------------------------------------
    wms_family_id = fields.Many2one(
        "wms.family",
        string="Family",
        help="The generic product / molecule (Paracetamol, Cow Feed). Type to "
        "search; use ＋ Create and edit to add a new one with its code.",
    )
    wms_brand_id = fields.Many2one("wms.brand", string="Brand")
    wms_form_id = fields.Many2one("wms.form", string="Form / Model")
    wms_variant = fields.Char(string="Variant")
    wms_dosage = fields.Char(string="Strength / dosage / concentration")
    wms_pack_size = fields.Char(string="Pack size")
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit",
        compute="_compute_uom",
        readonly=False,
        store=True,
        help="Stock unit. Suggested from the Form (tablet → Units, syrup → L) or "
        "the Kind; change it before saving if needed.",
    )
    name = fields.Char(string="Product name", required=True)
    standard_price = fields.Float(string="Unit cost (optional)")

    # ---- category-driven 'required' flags (for the view) ----------------
    req_brand = fields.Boolean(related="categ_id.wms_effective_req_brand")
    req_form = fields.Boolean(related="categ_id.wms_effective_req_form")
    req_strength = fields.Boolean(related="categ_id.wms_effective_req_strength")
    req_pack = fields.Boolean(compute="_compute_req_pack")
    form_is_model = fields.Boolean(related="categ_id.wms_form_is_model")

    # ---- live previews --------------------------------------------------
    sku_preview = fields.Char(string="SKU", compute="_compute_preview")
    code128_preview = fields.Char(string="Code128", compute="_compute_preview")
    pid_preview = fields.Char(string="Internal code", compute="_compute_preview")
    ean_preview = fields.Char(string="EAN-13", compute="_compute_preview")
    dup_warning = fields.Char(compute="_compute_preview")

    # --------------------------------------------------------------------
    # Computes
    # --------------------------------------------------------------------
    @api.depends("categ_id")
    def _compute_kind(self):
        for w in self:
            w.wms_product_kind = w.categ_id.wms_default_kind or "consumable"

    @api.depends("categ_id")
    def _compute_req_pack(self):
        # The owner's universal model uses one "Pack size"; a category that flags
        # either Size or Pack as required makes the wizard's Pack field required.
        for w in self:
            w.req_pack = bool(
                w.categ_id.wms_effective_req_pack or w.categ_id.wms_effective_req_size
            )

    @api.depends("wms_form_id", "wms_product_kind")
    def _compute_uom(self):
        for w in self:
            uom = w.wms_form_id.default_uom_id
            if not uom and w.wms_product_kind:
                xmlid = KIND_DEFAULT_UOM.get(w.wms_product_kind, _KIND_DEFAULT_UOM_FALLBACK)
                uom = self.env.ref(xmlid, raise_if_not_found=False)
            w.uom_id = uom.id if uom else False

    def _identity_vals(self):
        self.ensure_one()
        return {
            "wms_product_kind": self.wms_product_kind,
            "wms_family_id": self.wms_family_id.id,
            "wms_brand_id": self.wms_brand_id.id,
            "wms_form_id": self.wms_form_id.id,
            "wms_variant": self.wms_variant,
            "wms_dosage": self.wms_dosage,
            "wms_pack_size": self.wms_pack_size,
        }

    def _peek_seq(self, code):
        seq = self.env["ir.sequence"].sudo().search([("code", "=", code)], limit=1)
        return seq.number_next_actual if seq else 0

    @api.depends(
        "wms_product_kind",
        "wms_family_id",
        "wms_brand_id",
        "wms_form_id",
        "wms_variant",
        "wms_dosage",
        "wms_pack_size",
    )
    def _compute_preview(self):
        Tmpl = self.env["product.template"]
        for w in self:
            sku = Tmpl._wms_compose_business_sku(w._identity_vals())
            w.sku_preview = sku or False
            w.code128_preview = sku or False
            # PRD + EAN-13 are sequence-assigned at create; show the NEXT value as
            # an indicative preview (read-only peek, does not consume the number).
            n = w._peek_seq("wms.product.code")
            w.pid_preview = ("PRD-%06d" % n) if n else _("(assigned on create)")
            m = w._peek_seq("wms.barcode.ean13")
            if m:
                body = "02" + str(m).zfill(10)
                w.ean_preview = body + Tmpl._ean13_checksum(body)
            else:
                w.ean_preview = _("(assigned on create)")
            # Live duplicate heads-up (the hard block is in product.template.create).
            dup = False
            if sku:
                existing = (
                    self.env["product.product"]
                    .with_context(active_test=False)
                    .search([("default_code", "=", sku)], limit=1)
                )
                if existing:
                    dup = _("A product with SKU %(sku)s already exists: %(name)s") % {
                        "sku": sku,
                        "name": existing.display_name,
                    }
            w.dup_warning = dup

    # --------------------------------------------------------------------
    # Name suggestion
    # --------------------------------------------------------------------
    @api.onchange("wms_family_id", "wms_brand_id", "wms_form_id", "wms_dosage", "wms_pack_size")
    def _onchange_suggest_name(self):
        """Pre-fill a readable display name from the identity (the admin can edit
        it). Only fills when the name is still empty or matches a prior suggestion
        so it never clobbers a name the admin typed by hand."""
        for w in self:
            if w._origin.name and w.name == w._origin.name:
                continue
            parts = [
                w.wms_family_id.name,
                w.wms_dosage,
                w.wms_form_id.name,
                w.wms_pack_size,
            ]
            base = " ".join(p for p in parts if p)
            if w.wms_brand_id and base:
                base = "%s (%s)" % (base, w.wms_brand_id.name)
            if base and not (w.name and w.name != base):
                w.name = base

    # --------------------------------------------------------------------
    # Create
    # --------------------------------------------------------------------
    def _check_required(self):
        self.ensure_one()
        missing = []
        if not self.wms_family_id:
            missing.append(_("Family"))
        if self.req_brand and not self.wms_brand_id:
            missing.append(_("Brand"))
        if self.req_form and not self.wms_form_id:
            missing.append(_("Form / Model"))
        if self.req_strength and not self.wms_dosage:
            missing.append(_("Strength"))
        if self.req_pack and not self.wms_pack_size:
            missing.append(_("Pack size"))
        if missing:
            raise UserError(
                _(
                    "This category requires: %s.\nFill them in so the product is "
                    "properly classified and gets a complete SKU."
                )
                % ", ".join(missing)
            )

    def _create_product(self):
        self.ensure_one()
        self._check_required()
        vals = {
            "name": self.name,
            "type": "consu",
            "is_storable": True,
            "categ_id": self.categ_id.id,
            "wms_product_kind": self.wms_product_kind,
            "wms_family_id": self.wms_family_id.id,
            "wms_brand_id": self.wms_brand_id.id,
            "wms_form_id": self.wms_form_id.id,
            "wms_variant": self.wms_variant or False,
            "wms_dosage": self.wms_dosage or False,
            "wms_pack_size": self.wms_pack_size or False,
        }
        if self.uom_id:
            vals["uom_id"] = self.uom_id.id
        if self.standard_price:
            vals["standard_price"] = self.standard_price
        # product.template.create() composes the Business SKU, stamps the PRD
        # code, mints the barcodes and BLOCKS a duplicate identity.
        return self.env["product.template"].create(vals)

    def action_create(self):
        tmpl = self._create_product()
        return {
            "type": "ir.actions.act_window",
            "name": tmpl.display_name,
            "res_model": "product.template",
            "res_id": tmpl.id,
            "view_mode": "form",
            "views": [(self.env.ref("product.product_template_only_form_view").id, "form")],
            "target": "current",
        }

    def action_create_and_new(self):
        self._create_product()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Product"),
            "res_model": "wms.product.create",
            "view_mode": "form",
            "target": "current",
            "context": {"default_categ_id": self.categ_id.id},
        }

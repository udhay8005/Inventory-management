"""V20-002 — extend the WMS kind machinery with the new perishable kinds
(vaccine, supplement, chemical, fertilizer, food) WITHOUT editing the frozen
v19 addons (touch-point E1 in docs/v20-perishable-engine/02-touch-point-map.md).

The v19 kind metadata lives in module-level lookup tables in
``wms_location.models.product_template``. We extend them IN PLACE — mutating the
mutable dict/list objects (so every holder of the SAME object, including the v19
methods that read them, observes the new entries) and REBINDING the one
``frozenset`` (``EXPIRY_SENSITIVE_KINDS``), whose sole reader
(``stock_quant._wms_sorted_for_removal``) does a per-call local import and so
picks up the rebind. The frozen v19 source files are never touched.
"""

from odoo import api, fields, models
from odoo.addons.wms_location.models import product_template as _v19

# New perishable kinds (key, label). Label echoes the SKU prefix, matching the
# v19 convention so the create-form preview shows the SKU shape before save.
NEW_PERISHABLE_KINDS = [
    ("vaccine", "Vaccine - veterinary (VAC)"),
    ("supplement", "Supplement / Mineral mix (SUPP)"),
    ("chemical", "Chemical / Disinfectant (CHEM)"),
    ("fertilizer", "Fertilizer / Manure (FERT)"),
    ("food", "Food / Provisions (FOOD)"),
]
_NEW_PREFIX = {
    "vaccine": "VAC",
    "supplement": "SUPP",
    "chemical": "CHEM",
    "fertilizer": "FERT",
    "food": "FOOD",
}
_NEW_SEQ = {k: "wms.sku.%s" % k for k in _NEW_PREFIX}
# UoM defaults: fertilizer is weighed (kg, like feed); the rest are counted
# (Units). A specific liquid chemical is flipped to Litre by hand on the product
# form — same rationale as v19 medicine/plumbing (avoid arming the measured-item
# photo gate for counted vials/sachets).
_NEW_UOM = {
    "vaccine": "uom.product_uom_unit",
    "supplement": "uom.product_uom_unit",
    "chemical": "uom.product_uom_unit",
    "fertilizer": "uom.product_uom_kgm",
    "food": "uom.product_uom_unit",
}
# All five are consumed, not returned.
_NEW_RETURNABLE = {k: False for k in _NEW_PREFIX}


def _extend_v19_kind_tables():
    """Extend the v19 lookup tables in place (idempotent)."""
    existing = dict(_v19.WMS_KIND_SELECTION)
    for key, label in NEW_PERISHABLE_KINDS:
        if key not in existing:
            _v19.WMS_KIND_SELECTION.append((key, label))
    _v19.KIND_SKU_PREFIX.update(_NEW_PREFIX)
    _v19.KIND_SEQ_CODE.update(_NEW_SEQ)
    _v19.KIND_DEFAULT_UOM.update(_NEW_UOM)
    _v19.KIND_RETURNABLE_DEFAULTS.update(_NEW_RETURNABLE)
    # frozenset → rebind (its sole reader re-imports the name per call).
    _v19.EXPIRY_SENSITIVE_KINDS = frozenset(_v19.EXPIRY_SENSITIVE_KINDS | set(_NEW_PREFIX))


_extend_v19_kind_tables()


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Make the five new perishable kinds selectable on the existing field. The
    # SKU prefix / sequence / UoM / returnable behaviour comes from the v19
    # tables we extended above.
    wms_product_kind = fields.Selection(
        selection_add=NEW_PERISHABLE_KINDS,
        ondelete={k: "set null" for k, _ in NEW_PERISHABLE_KINDS},
    )

    # V20-022 — per-product shelf-life overrides (functional spec §2.8). These
    # are DISTINCT from the v19 ``wms_min_life_days`` (a per-department min
    # re-request interval feeding the Scan Issue approval gate). 0 = no override,
    # fall back to the kind policy (wms.shelf.life.policy) then the global param.
    wms_shelf_life_days = fields.Integer(
        string="Total shelf life (override)",
        help="Per-product total shelf life in days. 0 = use this product's kind "
        "policy. Informational.",
    )
    wms_min_receive_life_days = fields.Integer(
        string="Min shelf life @ receipt (override)",
        help="Per-product minimum remaining shelf life (days) to RECEIVE without a "
        "manager override. 0 = use the kind policy, then the global setting. "
        "Distinct from 'Min re-request interval'.",
    )
    wms_min_issue_life_days = fields.Integer(
        string="Min shelf life @ issue (override)",
        help="Per-product minimum remaining shelf life (days) to ISSUE without a "
        "manager override. 0 = use the kind policy, then the global setting.",
    )

    def _wms_resolve_shelf_life(self):
        """Resolve (total, min_receive, min_issue) shelf-life days for this
        product (V20-022 / spec §2.8). Precedence, per field: a non-zero
        per-product override wins; else the per-kind policy row; else the global
        fallback parameter. Returns a dict with keys total / min_receive /
        min_issue (all ints, >= 0)."""
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo()
        try:
            g_recv = int(param.get_param("wms_perishable.min_receive_shelf_life_days", "60") or 0)
        except (TypeError, ValueError):
            g_recv = 60
        try:
            g_issue = int(param.get_param("wms_perishable.min_issue_shelf_life_days", "0") or 0)
        except (TypeError, ValueError):
            g_issue = 0
        policy = self.env["wms.shelf.life.policy"]._policy_for_kind(self.wms_product_kind)
        p_total = policy.total_days if policy else 0
        p_recv = policy.min_receive_days if policy else 0
        p_issue = policy.min_issue_days if policy else 0
        return {
            "total": self.wms_shelf_life_days or p_total or 0,
            "min_receive": self.wms_min_receive_life_days or p_recv or g_recv,
            "min_issue": self.wms_min_issue_life_days or p_issue or g_issue,
        }

    @api.model_create_multi
    def create(self, vals_list):
        # V20-003: a perishable product is lot-tracked with expiry from creation
        # — the only safe point to enable tracking (before it can hold stock).
        # NEW products only; existing stock is migrated via the legacy-lot path
        # (V20-020). Non-perishables are untouched, preserving v19 behaviour.
        # setdefault so an explicit caller value always wins.
        for vals in vals_list:
            if vals.get("wms_product_kind") in _v19.EXPIRY_SENSITIVE_KINDS:
                vals.setdefault("tracking", "lot")
                vals.setdefault("use_expiration_date", True)
        return super().create(vals_list)


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        # V20-003: perishables must be lot-tracked regardless of the creation
        # path. The guided wizard goes through product.template.create (handled
        # above), but onboard / CSV import / direct product.product.create do
        # NOT route through that override — so enable it here too. The template
        # fields land on the auto-created template via the _inherits delegation.
        for vals in vals_list:
            if vals.get("wms_product_kind") in _v19.EXPIRY_SENSITIVE_KINDS:
                vals.setdefault("tracking", "lot")
                vals.setdefault("use_expiration_date", True)
        return super().create(vals_list)

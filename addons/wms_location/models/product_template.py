from odoo import api, fields, models

# Default returnability per WMS kind. The Admin can still override
# per-product on the form (`wms_is_returnable` is read/write — the
# compute only seeds it from the kind, the Admin can flip the boolean
# afterwards if a supplier accepts a partially-used batch back, etc.).
#
# Single-use / consumable things (petrol, screws once welded in,
# food, …) are NOT returnable: once they leave the warehouse they're
# either spent, contaminated, or impossible to reseal. Tools and spare
# parts ARE returnable because they survive use.
KIND_RETURNABLE_DEFAULTS = {
    "raw_material": True,
    "packaging": True,
    "fluid": False,
    "finished_good": True,
    "wip": True,
    "consumable": False,
    "tool": True,
    "spare": True,
}

WMS_KIND_SELECTION = [
    ("raw_material", "Raw Material (RM)"),
    ("packaging", "Packaging (PK)"),
    ("fluid", "Fluid / Liquid / Oil (FL)"),
    ("finished_good", "Finished Good (FG)"),
    ("wip", "Work in Progress (WIP)"),
    ("consumable", "Consumable (CONS)"),
    ("tool", "Tool / Equipment (TOOL)"),
    ("spare", "Spare Part (SPARE)"),
]


class ProductTemplate(models.Model):
    """WMS classification + returnability — defined on product.template
    so it's shared across product variants. The matching fields are
    surfaced on product.product via related fields below.

    The Admin (WMS / Manager) sets the kind once at product creation.
    The Store Keeper sees these fields read-only on the product form
    (enforced by Odoo's product ACL: stock.group_stock_user has read
    only) and the Scan Return wizard refuses any product whose
    `wms_is_returnable` is False.
    """

    _inherit = "product.template"

    wms_product_kind = fields.Selection(
        WMS_KIND_SELECTION,
        string="WMS Kind",
        index=True,
        tracking=True,
        help="Classification used by WMS for returnability and audit "
        "reporting. Mirrors the SKU prefix convention "
        "(RM/PK/FL/FG/WIP/CONS/TOOL/SPARE).",
    )

    wms_is_returnable = fields.Boolean(
        string="Returnable",
        compute="_compute_wms_is_returnable",
        store=True,
        readonly=False,  # admin can override the kind-derived default
        tracking=True,
        help="When ticked, this product can be received back into stock "
        "via Scan Return (e.g. a tool came back from production). "
        "Auto-set from WMS Kind: tools/spares/raw materials default to "
        "returnable; fluids and consumables default to NOT returnable, "
        "because petrol once dispensed can't come back into a barrel "
        "and screws once welded in can't be unscrewed onto a shelf.",
    )

    @api.depends("wms_product_kind")
    def _compute_wms_is_returnable(self):
        """Seed returnability from kind on first set, but leave existing
        overrides alone on re-compute (e.g. when other fields change)."""
        for p in self:
            if p.wms_product_kind:
                p.wms_is_returnable = KIND_RETURNABLE_DEFAULTS.get(p.wms_product_kind, True)


class ProductProduct(models.Model):
    """Expose template-level WMS classification on the variant model so
    other wms_* addons can write `product.wms_is_returnable` directly
    instead of going through `product.product_tmpl_id.wms_is_returnable`.
    """

    _inherit = "product.product"

    wms_product_kind = fields.Selection(
        related="product_tmpl_id.wms_product_kind",
        store=True,
        readonly=False,
        string="WMS Kind",
    )
    wms_is_returnable = fields.Boolean(
        related="product_tmpl_id.wms_is_returnable",
        store=True,
        readonly=False,
        string="Returnable",
    )

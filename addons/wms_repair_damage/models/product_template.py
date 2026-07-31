"""Stock breakdown on the product form (UAT R3).

The operator's exact words during the damage/repair walkthrough: "if the
product is repair means the total count decrease happen right — is not
noting here." The plain on-hand number silently shrinks when a unit goes
to Damage or Repair-Out, with nothing on the product saying WHERE it went.

These four computed figures split the internal on-hand into the places an
operator actually thinks in: on the shelf (issuable), out in use at the
trust, quarantined as damaged, and away under repair.
"""

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    wms_qty_on_shelf = fields.Float(
        string="On shelf",
        compute="_compute_wms_stock_breakdown",
        help="Issuable stock sitting in storage slots / floor zones.",
    )
    wms_qty_in_use = fields.Float(
        string="Out in use",
        compute="_compute_wms_stock_breakdown",
        help="Issued to the trust-use location and not yet returned.",
    )
    wms_qty_damaged = fields.Float(
        string="Damaged",
        compute="_compute_wms_stock_breakdown",
        help="Quarantined in the Damage location — excluded from issuing.",
    )
    wms_qty_under_repair = fields.Float(
        string="Under repair",
        compute="_compute_wms_stock_breakdown",
        help="Away in the Repair-Out location — comes back via Mark Done.",
    )

    def _compute_wms_stock_breakdown(self):
        Quant = self.env["stock.quant"]
        trust = self.env.ref("wms_location.stock_location_trust_use", raise_if_not_found=False)
        trust_path = trust.parent_path if trust else None
        for tmpl in self:
            shelf = in_use = damaged = repair = 0.0
            variants = tmpl.product_variant_ids
            if variants:
                quants = Quant.search(
                    [
                        ("product_id", "in", variants.ids),
                        ("location_id.usage", "=", "internal"),
                        ("quantity", "!=", 0),
                    ]
                )
                for quant in quants:
                    loc = quant.location_id
                    if loc.wms_is_damage:
                        damaged += quant.quantity
                    elif loc.wms_is_repair:
                        repair += quant.quantity
                    elif trust_path and (loc.parent_path or "").startswith(trust_path):
                        in_use += quant.quantity
                    else:
                        shelf += quant.quantity
            tmpl.wms_qty_on_shelf = shelf
            tmpl.wms_qty_in_use = in_use
            tmpl.wms_qty_damaged = damaged
            tmpl.wms_qty_under_repair = repair

"""Wave 2 — shared supplier links.

Supplier analytics needs every quality event attributable to a supplier. Wave 1
stores the supplier on the lot (stock.lot.wms_supplier_id) and the recall
(wms.lot.recall.supplier_id), but damage and quarantine carry none. These
additive _inherit extensions add a stored supplier column to both so the
scorecard SQL view can aggregate damaged / rejected goods per partner.
"""

from odoo import api, fields, models


class WmsDamage(models.Model):
    _inherit = "wms.damage"

    wms_supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        compute="_compute_wms_supplier_id",
        store=True,
        readonly=False,
        help="Supplier the damaged goods came from (defaults to the product's "
        "main vendor; editable). Drives the supplier quality scorecard.",
    )

    @api.depends("product_id")
    def _compute_wms_supplier_id(self):
        for rec in self:
            if not rec.wms_supplier_id:
                sellers = rec.product_id.seller_ids
                rec.wms_supplier_id = sellers[:1].partner_id.id if sellers else False


class WmsLotQuarantine(models.Model):
    _inherit = "wms.lot.quarantine"

    wms_supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        compute="_compute_wms_supplier_id",
        store=True,
        help="Supplier of the held lots (from the first lot carrying one). Drives "
        "the supplier acceptance/rejection rate.",
    )

    @api.depends("lot_ids")
    def _compute_wms_supplier_id(self):
        for rec in self:
            lots = rec.lot_ids.filtered("wms_supplier_id")
            rec.wms_supplier_id = lots[:1].wms_supplier_id.id if lots else False

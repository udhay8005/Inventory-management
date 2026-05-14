from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    wms_is_damage = fields.Boolean(
        string="Holds damaged stock",
        help="Internal location where damaged stock is held until repaired or scrapped.",
    )
    wms_is_repair = fields.Boolean(
        string="Holds in-repair stock",
        help="Internal location where stock currently being repaired lives.",
    )

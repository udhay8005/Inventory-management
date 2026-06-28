"""V20-011c — let the Damage flow reserve EXPIRED stock for disposal.

Once perishables are lot-tracked, product_expiry blocks expired stock from ALL
reservation — so expired stock would be un-issuable (correct) AND un-disposable
(stuck on the shelf with no way to clear it). Expired stock is cleared by
DAMAGING it (moving it to the Damage location, then a Wave-2 write-off). We run
the damage confirmation with the carve-out flag so its reservation can pull
expired lots; the flag is read by stock.quant._get_gather_domain (V20-011c).

The flag is scoped to the damage flow only — normal Scan Issue still excludes
expired stock. The damage event itself carries the existing authorization /
audit fields (reported-by / authorized-by / store-keeper), so disposing expired
stock is already an audited, authorized action.
"""

from odoo import models


class WmsDamage(models.Model):
    _inherit = "wms.damage"

    def action_confirm(self):
        return super(WmsDamage, self.with_context(wms_allow_expired_removal=True)).action_confirm()

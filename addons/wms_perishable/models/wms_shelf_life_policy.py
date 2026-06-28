"""V20-022 — per-kind shelf-life policy (functional spec §2.8).

A small admin-editable table: each perishable kind carries a total shelf life,
a minimum life required at RECEIPT, and a minimum life required at ISSUE. A
product may override any of these on its own form; absent both the policy and a
product override, a global fallback parameter applies.

The receipt guard (``scan_receipt._wms_short_dated_lines``) and the new
short-dated-issue guard (``scan_issue._wms_short_dated_issue_lines``) both read
this through ``product.template._wms_resolve_shelf_life()``. The frozen v19
addons are not touched — this is a new model owned by wms_perishable.
"""

from odoo import api, fields, models

# Imported at module load (after product_template extended the kind tables, per
# the models/__init__ import order). The selection is resolved at RUNTIME via a
# lambda so the five new perishable kinds are included.
from odoo.addons.wms_location.models.product_template import WMS_KIND_SELECTION


class WmsShelfLifePolicy(models.Model):
    _name = "wms.shelf.life.policy"
    _description = "WMS perishable shelf-life policy (per kind)"
    _order = "product_kind"
    _rec_name = "product_kind"

    product_kind = fields.Selection(
        selection=lambda self: list(WMS_KIND_SELECTION),
        string="Product kind",
        required=True,
        help="The WMS kind this shelf-life policy applies to.",
    )
    total_days = fields.Integer(
        string="Total shelf life (days)",
        help="Typical total shelf life for this kind. 0 = per product / not enforced.",
    )
    min_receive_days = fields.Integer(
        string="Min @ receipt (days)",
        help="Minimum remaining shelf life to RECEIVE this kind without a manager "
        "override. 0 = fall back to the global setting.",
    )
    min_issue_days = fields.Integer(
        string="Min @ issue (days)",
        help="Minimum remaining shelf life to ISSUE this kind without a manager "
        "override. 0 = fall back to the global setting.",
    )
    active = fields.Boolean(default=True)

    _kind_unique = models.Constraint(
        "UNIQUE(product_kind)",
        "Each product kind can have only one shelf-life policy.",
    )
    _receive_non_negative = models.Constraint(
        "CHECK(min_receive_days >= 0 AND min_issue_days >= 0 AND total_days >= 0)",
        "Shelf-life days cannot be negative.",
    )

    @api.model
    def _policy_for_kind(self, kind):
        """Return the active policy record for ``kind`` (empty recordset if none)."""
        if not kind:
            return self.browse()
        return self.search([("product_kind", "=", kind), ("active", "=", True)], limit=1)

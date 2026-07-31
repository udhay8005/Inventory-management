"""V20-022 — global shelf-life fallback settings.

Follows the project's existing config pattern (a small TransientModel wizard,
like wms_reports' Google-Drive settings) rather than res.config.settings — the
two global fallbacks are stored as ``ir.config_parameter`` so an admin can edit
them from a menu instead of Technical > System Parameters. Per-kind rows in
``wms.shelf.life.policy`` and per-product overrides both take precedence over
these globals.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError

PARAM_RECEIVE = "wms_perishable.min_receive_shelf_life_days"
PARAM_ISSUE = "wms_perishable.min_issue_shelf_life_days"


class WmsShelfLifeSettings(models.TransientModel):
    _name = "wms.shelf.life.settings"
    _description = "WMS perishable shelf-life settings"

    min_receive_days = fields.Integer(
        string="Global min shelf life @ receipt (days)",
        default=60,
        help="Fallback minimum days of shelf life required to RECEIVE a perishable "
        "without a manager override, for kinds without their own policy row. "
        "0 disables the global receipt guard.",
    )
    min_issue_days = fields.Integer(
        string="Global min shelf life @ issue (days)",
        default=0,
        help="Fallback minimum days of shelf life required to ISSUE a perishable "
        "without a manager override, for kinds without their own policy row. "
        "0 disables the global issue guard.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        param = self.env["ir.config_parameter"].sudo()
        try:
            res["min_receive_days"] = int(param.get_param(PARAM_RECEIVE, "60") or 0)
        except (TypeError, ValueError):
            res["min_receive_days"] = 60
        try:
            res["min_issue_days"] = int(param.get_param(PARAM_ISSUE, "0") or 0)
        except (TypeError, ValueError):
            res["min_issue_days"] = 0
        return res

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError("Only a Manager can change the shelf-life settings.")
        if self.min_receive_days < 0 or self.min_issue_days < 0:
            raise UserError("Shelf-life days cannot be negative.")
        param = self.env["ir.config_parameter"].sudo()
        param.set_param(PARAM_RECEIVE, str(self.min_receive_days))
        param.set_param(PARAM_ISSUE, str(self.min_issue_days))
        return {"type": "ir.actions.act_window_close"}

    def action_open_policy(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "wms_perishable.action_wms_shelf_life_policy"
        )

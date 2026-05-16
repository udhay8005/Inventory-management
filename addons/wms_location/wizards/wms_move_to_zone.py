from odoo import fields, models
from odoo.exceptions import UserError


class WmsMoveToZone(models.TransientModel):
    """Batch-reparent selected racks / floor zones into a chosen zone.

    Used when you've already generated locations under WH/Stock and now
    want to organise them: e.g. the existing 32 racks live directly under
    WH/Stock and should be moved into a newly-created "1st Floor" zone.

    Reparenting is safe — Odoo's stock.location parent_path is maintained
    automatically, and existing quants don't move.
    """

    _name = "wms.move.to.zone"
    _description = "Batch-move racks/floors into a zone"

    location_ids = fields.Many2many(
        "stock.location",
        string="Locations to move",
        domain=[("wms_location_type", "in", ("rack", "floor"))],
    )
    target_zone_id = fields.Many2one(
        "stock.location",
        string="Target zone",
        required=True,
        domain=[("wms_location_type", "=", "zone")],
        help="The zone they will live under.",
    )

    def action_move(self):
        self.ensure_one()
        if not self.location_ids:
            raise UserError("Select at least one rack or floor zone.")
        if not self.target_zone_id:
            raise UserError("Pick a target zone.")
        # Stock.location stores company_id; verify target zone is in the
        # same company to avoid the company-crossover constraint.
        for loc in self.location_ids:
            if loc.company_id and loc.company_id != self.target_zone_id.company_id:
                raise UserError(
                    "Location %s belongs to company %s but target zone is in %s."
                    % (
                        loc.display_name,
                        loc.company_id.display_name,
                        self.target_zone_id.company_id.display_name,
                    )
                )
        self.location_ids.write({"location_id": self.target_zone_id.id})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Moved",
                "message": (
                    "%d location(s) moved under zone %s."
                    % (len(self.location_ids), self.target_zone_id.display_name)
                ),
                "sticky": False,
            },
        }

# File: models/wms_animal.py
# Module: wms_pharmacy
# Description: Extends wms.animal with a One2many to wms.dispense.log and a
#              computed medication count. Adds an action to open the animal's
#              medication history directly from the animal form.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: wms.animal (wms_location), wms.dispense.log

from odoo import _, api, fields, models


class WmsAnimal(models.Model):
    """Pharmacy extension on wms.animal.

    Adds:
    * ``dispense_log_ids`` — One2many to all dispense events for this animal.
    * ``wms_medication_count`` — computed count shown on the smart button.
    * ``action_view_dispense_logs()`` — opens the full medication history list.

    Usage example::

        gauri = env['wms.animal'].browse(animal_id)
        gauri.wms_medication_count  # -> 12
        gauri.dispense_log_ids      # -> wms.dispense.log recordset
    """

    _inherit = "wms.animal"

    dispense_log_ids = fields.One2many(
        "wms.dispense.log",
        "animal_id",
        string="Medication history",
        readonly=True,
        help="All pharmaceutical dispense events recorded for this animal.",
    )
    wms_medication_count = fields.Integer(
        string="Medication events",
        compute="_compute_wms_medication_count",
        help="Total number of dispense events (doses) recorded for this animal.",
    )

    @api.depends("dispense_log_ids")
    def _compute_wms_medication_count(self):
        """Count dispense log rows for each animal.

        :returns: void — writes ``wms_medication_count`` on each record.
        """
        for animal in self:
            animal.wms_medication_count = len(animal.dispense_log_ids)

    def action_view_dispense_logs(self):
        """Open the full medication history list for this animal.

        :returns: dict — ``ir.actions.act_window`` opening the dispense log
            list/form filtered to this animal.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Medication history — %s") % (self.name or ""),
            "res_model": "wms.dispense.log",
            "view_mode": "list,form",
            "domain": [("animal_id", "=", self.id)],
            "context": {
                "default_animal_id": self.id,
                "create": False,
            },
        }

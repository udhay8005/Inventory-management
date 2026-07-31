from odoo import fields, models


class WmsPurpose(models.Model):
    """Reason an item is issued (treatment, vaccination, consumption, …).

    Optional second dimension alongside the department; admin-editable
    and archivable so historical pickings stay readable.
    """

    _name = "wms.purpose"
    _description = "Issue purpose / reason"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    note = fields.Char()

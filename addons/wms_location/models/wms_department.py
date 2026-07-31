from odoo import fields, models


class WmsDepartment(models.Model):
    """Issue department / cost centre for Scan Issue.

    Replaces the old fixed ``WMS_ISSUED_FOR_SELECTION`` codes with an
    admin-editable register so the trust can carve out finer cost
    centres (Veterinary, Dairy, Fodder, …) without a code change.

    ``legacy_issued_for`` records which old selection key a department
    maps back to so the legacy ``wms_issued_for`` column and the
    Consumption report keep reconciling during the transition; the
    wms_barcode back-fill migration reads it. Departments are archived
    (``active=False``), never deleted, so historical pickings stay
    readable.
    """

    _name = "wms.department"
    _description = "Issue department / cost centre"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True, index=True)
    code = fields.Char(
        required=True,
        index=True,
        help="Stable short code used to map legacy wms_issued_for values.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    legacy_issued_for = fields.Char(
        help="Old WMS_ISSUED_FOR_SELECTION key this department was seeded "
        "from (or blank), kept for reporting reconciliation.",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Department code must be unique.",
    )

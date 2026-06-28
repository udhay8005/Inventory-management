# File: models/wms_dispense_log.py
# Module: wms_pharmacy
# Description: Pharmaceutical dispensing genealogy log (wms.dispense.log).
#              Each row is an immutable record of one dispense event: which
#              product (and lot/batch), how many tablets, which animal, how
#              many strips were opened, and a full snapshot of the packaging
#              counts at dispense time for traceability even if the product
#              is later reconfigured.
# Author: Senior Dev Architect
# Created: 2026-06-09
# Dependencies: product.product, stock.lot, wms.animal, res.users, stock.picking

from odoo import fields, models
from odoo.exceptions import UserError

# Genealogy content that must never change once recorded (the pharmaceutical
# audit trail). animal_id / picking_id are intentionally excluded so their
# ondelete='set null' cascades still work; note stays editable.
_PROTECTED_FIELDS = frozenset(
    {
        "product_id",
        "lot_id",
        "quantity",
        "strips_opened",
        "tablets_per_strip",
        "tablets_per_box",
        "dispense_date",
        "dispensed_by",
    }
)


class WmsDispenseLog(models.Model):
    """Pharmaceutical genealogy + medication history log.

    Created by ``wms.dispense.wizard.action_dispense()`` and never edited
    afterwards. Stores a frozen snapshot of the packaging counts (tablets_per_strip,
    tablets_per_box) so the audit trail remains valid even if the product
    configuration changes later.

    The combination of ``lot_id`` (batch traceability) + ``product_id`` +
    ``animal_id`` + ``dispense_date`` answers "which batch of Oxytetracycline
    was given to cow Gauri on 12-Jun-2026 and how many strips were opened?"

    Grouped by animal → Medication History report.
    Grouped by lot → Box→Strip→Tablet genealogy report.

    Usage example::

        log = env['wms.dispense.log'].search([('animal_id', '=', gauri.id)])
        for entry in log:
            print(entry.product_id.display_name, entry.quantity, 'tablets',
                  entry.dispense_date)
    """

    _name = "wms.dispense.log"
    _description = "Pharmaceutical dispense genealogy log"
    _rec_name = "product_id"
    _order = "dispense_date desc"

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
        ondelete="restrict",
        help="The packaged medicine that was dispensed.",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot / Batch",
        required=True,
        index=True,
        ondelete="restrict",
        help="The lot (batch) drawn. Enables traceability: 'which animals "
        "received stock from lot X?' (critical during a recall).",
    )
    animal_id = fields.Many2one(
        "wms.animal",
        string="Animal",
        index=True,
        ondelete="set null",
        help="The animal this dose was administered to (optional). "
        "Enables the per-animal Medication History report.",
    )
    quantity = fields.Integer(
        string="Tablets dispensed",
        required=True,
        help="Number of individual tablets dispensed in this event.",
    )
    dispense_date = fields.Datetime(
        string="Dispense date",
        default=fields.Datetime.now,
        required=True,
        index=True,
        help="Date and time of the dispense event.",
    )
    strips_opened = fields.Integer(
        string="Sealed strips opened",
        default=0,
        help="Number of physically sealed strips that were broken open to "
        "fulfil this dispense (0 when the dose was served entirely from an "
        "already-open strip).",
    )
    tablets_per_strip = fields.Integer(
        string="Tablets per strip (snapshot)",
        help="Snapshot of the product's tablets_per_strip at dispense time. "
        "Frozen so the genealogy stays valid even if the product is later "
        "reconfigured.",
    )
    tablets_per_box = fields.Integer(
        string="Tablets per box (snapshot)",
        help="Snapshot of the product's tablets_per_box at dispense time.",
    )
    dispensed_by = fields.Many2one(
        "res.users",
        string="Dispensed by",
        required=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
        help="The Odoo user who ran the dispense wizard.",
    )
    note = fields.Text(
        string="Note",
        help="Free-text note captured from the dispense wizard "
        "(e.g. treatment reason, dosage instructions).",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Issue picking",
        ondelete="set null",
        readonly=True,
        help="The outbound picking created for this dispense (if any). "
        "Provides a link to the full stock.move audit trail.",
    )

    def write(self, vals):
        """Append-only audit trail: the genealogy content cannot be edited once
        recorded (even by a manager). Cascade set-null on animal_id / picking_id
        and free-text note edits remain allowed."""
        if _PROTECTED_FIELDS.intersection(vals):
            raise UserError(
                "Dispense genealogy records are immutable — the pharmaceutical "
                "audit trail cannot be edited."
            )
        return super().write(vals)

    def unlink(self):
        """Append-only audit trail: genealogy records cannot be deleted."""
        raise UserError(
            "Dispense genealogy records cannot be deleted — they are the "
            "pharmaceutical audit trail."
        )

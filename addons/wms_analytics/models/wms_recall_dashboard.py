"""Wave 2 — Recall Dashboard.

Adds aggregate, reportable measures to each ``wms.lot.recall`` notice so the
trust can see — per recall, and grouped by supplier / state — how much of the
recalled stock has been issued out, how much is still on the shelf, how much
has been destroyed, and how much came back in. These are *roll-ups over the
recalled lots* (wms.lot.recall.lot_ids), not new lifecycle state:

  * issued_quantity    — total DONE out-moves of the recalled lots to a
                         customer / production / inventory-loss / transit sink
                         (left an internal storage location).
  * remaining_quantity — current on-hand of the recalled lots in live internal
                         storage (excludes the damage / repair sinks).
  * destroyed_quantity — quantity of the recalled lots whose lot is now in the
                         'destroyed' lifecycle state (wms_lot_state).
  * returned_quantity  — best-effort: total DONE in-moves of the recalled lots
                         back into internal storage from a customer / supplier.
  * is_open            — the recall is still active (state == 'active').

Additive ``_inherit`` of the Wave 1 recall model — no Wave 1 file is touched and
no recall flow changes. The fields are STORED so they can be used as pivot /
graph measures; they recompute whenever the recall's lot set or state changes.
The existing recall ACL covers the model, so no new access rows are needed.
"""

from odoo import api, fields, models


class WmsLotRecall(models.Model):
    _inherit = "wms.lot.recall"

    issued_quantity = fields.Float(
        string="Issued out",
        compute="_compute_recall_quantities",
        store=True,
        help="Total completed out-moves of the recalled lots that left internal "
        "storage (issued to a customer / production / loss / transit).",
    )
    remaining_quantity = fields.Float(
        string="Still on hand",
        compute="_compute_recall_quantities",
        store=True,
        help="Current on-hand quantity of the recalled lots in live internal "
        "storage (excludes the damage / repair sinks).",
    )
    destroyed_quantity = fields.Float(
        string="Destroyed",
        compute="_compute_recall_quantities",
        store=True,
        help="Quantity of recalled lots whose lot is now in the 'destroyed' " "lifecycle state.",
    )
    returned_quantity = fields.Float(
        string="Returned in",
        compute="_compute_recall_quantities",
        store=True,
        help="Best-effort total of completed in-moves of the recalled lots back "
        "into internal storage (returns from customer / supplier).",
    )
    is_open = fields.Boolean(
        string="Open",
        compute="_compute_is_open",
        store=True,
        help="True while the recall is active (not yet released).",
    )

    @api.depends("state")
    def _compute_is_open(self):
        for rec in self:
            rec.is_open = rec.state == "active"

    @api.depends("lot_ids", "lot_ids.wms_lot_state", "state")
    def _compute_recall_quantities(self):
        """Roll the recalled lots' movement / on-hand / lifecycle figures up
        onto each recall record.

        Out vs in is decided by the *usage* of the source and destination
        locations of each completed move line: a move whose source is internal
        and whose destination is NOT internal is an out-move (issue); the
        reverse is an in-move (return). Internal<->internal transfers net to
        zero and are ignored. On-hand is read from live internal storage,
        excluding the damage / repair sinks (the same exclusion the FEFO
        planner and the expiry-risk view use).
        """
        MoveLine = self.env["stock.move.line"]
        Quant = self.env["stock.quant"]

        for rec in self:
            lots = rec.lot_ids
            if not lots:
                rec.issued_quantity = 0.0
                rec.remaining_quantity = 0.0
                rec.destroyed_quantity = 0.0
                rec.returned_quantity = 0.0
                continue

            done_lines = MoveLine.search(
                [
                    ("lot_id", "in", lots.ids),
                    ("state", "=", "done"),
                    ("quantity", ">", 0),
                ]
            )
            issued = 0.0
            returned = 0.0
            for line in done_lines:
                src_internal = line.location_id.usage == "internal"
                dst_internal = line.location_dest_id.usage == "internal"
                if src_internal and not dst_internal:
                    issued += line.quantity
                elif dst_internal and not src_internal:
                    returned += line.quantity
            rec.issued_quantity = issued
            rec.returned_quantity = returned

            on_hand_quants = Quant.search(
                [
                    ("lot_id", "in", lots.ids),
                    ("location_id.usage", "=", "internal"),
                    ("location_id.wms_is_damage", "=", False),
                    ("location_id.wms_is_repair", "=", False),
                    ("quantity", ">", 0),
                ]
            )
            rec.remaining_quantity = sum(on_hand_quants.mapped("quantity"))

            destroyed_lots = lots.filtered(lambda lot: lot.wms_lot_state == "destroyed")
            if destroyed_lots:
                destroyed_quants = Quant.search(
                    [
                        ("lot_id", "in", destroyed_lots.ids),
                        ("quantity", ">", 0),
                    ]
                )
                rec.destroyed_quantity = sum(destroyed_quants.mapped("quantity"))
            else:
                rec.destroyed_quantity = 0.0

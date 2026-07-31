"""V20-014 — lot quarantine / QC hold.

Put suspect lots on hold pending a quality check: hold freezes them
(wms_lot_state='quarantine') and cancels their open reservations, the shared
issue planner gate (stock_location) then excludes them, and QC either RELEASES
them back to 'available' or REJECTS and DESTROYS them (wms_lot_state='destroyed',
also excluded; physical write-off is a manager Damage move — V20-011c carve-out
— with the formal write-off deferred to Wave 2). State-based (the V20-007 lot
lifecycle), consistent with recall (V20-013). Manager-gated.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsLotQuarantine(models.Model):
    _name = "wms.lot.quarantine"
    _description = "Lot quarantine / QC hold"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, copy=False, readonly=True, default="New")
    reason = fields.Text(required=True)
    lot_ids = fields.Many2many("stock.lot", string="Held lots", required=True)
    product_ids = fields.Many2many(
        "product.product",
        string="Affected products",
        compute="_compute_product_ids",
    )
    state = fields.Selection(
        [
            ("held", "On hold (QC)"),
            ("released", "Released"),
            ("rejected", "Rejected"),
            ("destroyed", "Destroyed"),
        ],
        default="held",
        required=True,
        index=True,
    )
    qc_notes = fields.Text(string="QC notes")
    held_on = fields.Datetime(readonly=True)
    held_by_id = fields.Many2one("res.users", string="Held by", readonly=True)
    decided_on = fields.Datetime(readonly=True)
    decided_by_id = fields.Many2one("res.users", string="Decided by", readonly=True)
    unreserved_count = fields.Integer(
        readonly=True,
        help="Open reservations cancelled when the lots were put on hold.",
    )

    @api.depends("lot_ids")
    def _compute_product_ids(self):
        for rec in self:
            rec.product_ids = rec.lot_ids.mapped("product_id")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.lot.quarantine") or "QC"
            # A QC hold freezes the lots on creation (the record IS the hold).
        records = super().create(vals_list)
        records._wms_apply_hold()
        return records

    def _check_manager(self):
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError("Only a Manager can quarantine, release, reject or destroy a lot.")

    def _wms_apply_hold(self):
        self._check_manager()
        for rec in self:
            if not rec.lot_ids:
                raise UserError("Add at least one lot to quarantine.")
            rec.lot_ids.write({"wms_lot_state": "quarantine"})
            open_lines = self.env["stock.move.line"].search(
                [
                    ("lot_id", "in", rec.lot_ids.ids),
                    ("state", "not in", ("done", "cancel")),
                    ("quantity", ">", 0),
                ]
            )
            open_lines.move_id._do_unreserve()
            rec.write(
                {
                    "held_on": fields.Datetime.now(),
                    "held_by_id": self.env.user.id,
                    "unreserved_count": len(open_lines),
                }
            )
            rec.lot_ids._wms_lifecycle_hook("quarantined", rec)  # V20-019

    def action_release(self):
        self._check_manager()
        for rec in self:
            if rec.state != "held":
                raise UserError("Only a lot currently on hold can be released.")
            rec.lot_ids.filtered(lambda lot: lot.wms_lot_state == "quarantine").write(
                {"wms_lot_state": "available"}
            )
            rec._wms_stamp_decision("released")
        return True

    def action_reject(self):
        self._check_manager()
        for rec in self:
            if rec.state != "held":
                raise UserError("Only a lot currently on hold can be rejected.")
            rec._wms_stamp_decision("rejected")
        return True

    def action_destroy(self):
        self._check_manager()
        for rec in self:
            if rec.state not in ("held", "rejected"):
                raise UserError("Only a held or rejected lot can be destroyed.")
            rec.lot_ids.filtered(
                lambda lot: lot.wms_lot_state in ("quarantine", "recalled", "available")
            ).write({"wms_lot_state": "destroyed"})
            rec._wms_stamp_decision("destroyed")
        return True

    @api.model
    def action_sweep_expired(self):
        """One click: put every EXPIRED batch that still holds stock on QC hold.

        The warehouse photos showed Povidone (exp 4/2025) and Zenbloat (exp
        10/2024) still sitting on the shelf in mid-2026. Expired stock beside
        good stock is the single most dangerous thing in a medicine room, and
        hunting it batch-by-batch is exactly the chore nobody does. This finds
        the lot, freezes it (quarantine excludes it from issuing) and hands the
        Manager one record to decide on — release after a check, or destroy.
        """
        self._check_manager()
        now = fields.Datetime.now()
        Quant = self.env["stock.quant"]
        # Batches still on an internal shelf, past their expiry, not already
        # held / recalled / destroyed.
        stocked = Quant.search([("quantity", ">", 0), ("location_id.usage", "=", "internal")])
        expired = stocked.mapped("lot_id").filtered(
            lambda lot: lot.expiration_date
            and lot.expiration_date <= now
            and lot.wms_lot_state == "available"
        )
        if not expired:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Nothing expired",
                    "message": "No expired batch is holding stock — the shelves are clean.",
                    "type": "success",
                    "sticky": False,
                },
            }
        products = ", ".join(sorted(set(expired.mapped("product_id.display_name")))[:6])
        record = self.create(
            {
                "reason": "Automatic expired-stock sweep on %s — %d batch(es) past "
                "their expiry date were still on the shelf: %s"
                % (fields.Date.context_today(self), len(expired), products),
                "lot_ids": [(6, 0, expired.ids)],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Expired stock swept into quarantine",
            "res_model": "wms.lot.quarantine",
            "res_id": record.id,
            "view_mode": "form",
        }

    def _wms_stamp_decision(self, state):
        self.write(
            {
                "state": state,
                "decided_on": fields.Datetime.now(),
                "decided_by_id": self.env.user.id,
            }
        )
        # V20-019 — 'released' / 'rejected' / 'destroyed' are lifecycle events.
        self.lot_ids._wms_lifecycle_hook(state, self)

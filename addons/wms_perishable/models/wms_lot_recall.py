"""V20-013 — lot recall: freeze recalled lots, cancel their open reservations,
keep them off the floor, and release them when cleared.

A recall sets each affected lot to wms_lot_state='recalled'. The shared issue
planner gate (stock_location.find_oldest_quants_for_product) then excludes
recalled lots from issue, and any OPEN reservation of a recalled lot is
cancelled at activation so an in-flight issue can't ship it. Releasing the
recall sets the lots back to 'available'. Who/when is recorded on the record
itself (immutable history via the draft→active→released state) and surfaced on
the lot via wms_lot_state (the RECALL-ACTIVE visibility). Manager-gated.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsLotRecall(models.Model):
    _name = "wms.lot.recall"
    _description = "Lot recall notice"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, copy=False, readonly=True, default="New")
    mode = fields.Selection(
        [("manual", "Internal / manual"), ("supplier", "Supplier notice")],
        required=True,
        default="manual",
    )
    supplier_id = fields.Many2one("res.partner", string="Supplier")
    supplier_notice_ref = fields.Char(string="Supplier notice ref")
    reason = fields.Text(required=True)
    lot_ids = fields.Many2many("stock.lot", string="Recalled lots", required=True)
    product_ids = fields.Many2many(
        "product.product",
        string="Affected products",
        compute="_compute_product_ids",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("released", "Released")],
        default="draft",
        required=True,
        index=True,
    )
    recalled_on = fields.Datetime(readonly=True)
    released_on = fields.Datetime(readonly=True)
    recalled_by_id = fields.Many2one("res.users", string="Recalled by", readonly=True)
    released_by_id = fields.Many2one("res.users", string="Released by", readonly=True)
    unreserved_count = fields.Integer(
        readonly=True,
        help="Open reservations cancelled when the recall was activated.",
    )

    @api.depends("lot_ids")
    def _compute_product_ids(self):
        for rec in self:
            rec.product_ids = rec.lot_ids.mapped("product_id")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("wms.lot.recall") or "RECALL"
        return super().create(vals_list)

    def _check_manager(self):
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError("Only a Manager can recall or release a lot.")

    def action_recall(self):
        self._check_manager()
        for rec in self:
            if rec.state != "draft":
                raise UserError("Only a draft recall can be activated.")
            if not rec.lot_ids:
                raise UserError("Add at least one lot before activating the recall.")
            # Freeze the lots so the issue planner excludes them.
            rec.lot_ids.write({"wms_lot_state": "recalled"})
            # Cancel any OPEN reservation holding a recalled lot, so an in-flight
            # issue can't ship recalled stock between plan and validate.
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
                    "state": "active",
                    "recalled_on": fields.Datetime.now(),
                    "recalled_by_id": self.env.user.id,
                    "unreserved_count": len(open_lines),
                }
            )
        return True

    def action_release(self):
        self._check_manager()
        for rec in self:
            if rec.state != "active":
                raise UserError("Only an active recall can be released.")
            # Only flip lots still in 'recalled' (don't resurrect destroyed ones).
            rec.lot_ids.filtered(lambda lot: lot.wms_lot_state == "recalled").write(
                {"wms_lot_state": "available"}
            )
            rec.write(
                {
                    "state": "released",
                    "released_on": fields.Datetime.now(),
                    "released_by_id": self.env.user.id,
                }
            )
        return True

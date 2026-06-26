"""V20-004 + V20-005 — make Scan Receipt lot-aware for perishables.

V20-004: the receipt line gains batch / expiry / supplier inputs.
V20-005: at validate, every lot-tracked line must carry a lot — find an
existing lot (company, product, batch) or create a new one, NEVER merging
distinct batches; auto-name (LOT-NNNNNN) when no batch was given, so a
perishable received without an explicit batch still validates. The lot's
expiry / supplier / manufacture metadata (V20-007 fields) are populated from
the line. Non-lot products are untouched (v19 behaviour preserved).

This _inherit-extends the frozen v19 wizard: we only PRE-SET line.lot_id before
the v19 action_validate runs, so its existing lot-carrying loop does the rest.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError


class WmsScanReceiptLine(models.TransientModel):
    _inherit = "wms.scan.receipt.line"

    wms_batch = fields.Char(
        string="Batch / Lot",
        help="Supplier batch number. Becomes the lot identity. Leave blank to "
        "auto-name (LOT-NNNNNN). A perishable line without a batch still receives.",
    )
    wms_expiry = fields.Date(
        string="Expiry",
        help="Expiry date for this batch. Defaults to the product's template "
        "expiry when left blank.",
    )
    wms_supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        help="Supplier this batch came from — stored on the lot for recall / traceability.",
    )


class WmsScanReceipt(models.TransientModel):
    _inherit = "wms.scan.receipt"

    def action_validate(self):
        # V20-018: refuse short-dated stock (less than the minimum receiving
        # shelf life) unless a Manager has approved it via the override below.
        if not self.env.context.get("wms_allow_short_dated"):
            short = self._wms_short_dated_lines()
            if short:
                raise UserError(self._wms_short_dated_message(short))
        # V20-005: ensure every lot-tracked line carries a lot BEFORE the v19
        # validate runs (its lot-carrying loop then lands the lot on the move
        # line). Idempotent — lines that already have a lot are left alone, so a
        # double-submit re-entry is a no-op here too.
        for line in self.line_ids:
            if line.product_id.tracking == "lot" and not line.lot_id:
                line.lot_id = self._wms_find_or_create_lot(line)
        res = super().action_validate()
        # V20-019 — fire the 'received' lifecycle hook for each received batch.
        for line in self.line_ids.filtered("lot_id"):
            line.lot_id._wms_lifecycle_hook("received", line)
        return res

    def _wms_min_receive_days(self):
        """Minimum shelf life (days) a perishable must have left to be received
        without a manager override. Global config, default 60 (OWNER-9); 0
        disables the guard. Per-kind shelf-life refinement is V20-022."""
        try:
            return int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("wms_perishable.min_receive_shelf_life_days", "60")
                or 0
            )
        except (TypeError, ValueError):
            return 0

    def _wms_line_expiry(self, line):
        return line.wms_expiry or line.product_id.product_tmpl_id.wms_expiry_date

    def _wms_short_dated_lines(self):
        days = self._wms_min_receive_days()
        out = self.env["wms.scan.receipt.line"]
        if days <= 0:
            return out
        today = fields.Date.today()
        for line in self.line_ids:
            if line.product_id.tracking != "lot":
                continue
            exp = self._wms_line_expiry(line)
            if exp and (exp - today).days < days:
                out |= line
        return out

    def _wms_short_dated_message(self, lines):
        days = self._wms_min_receive_days()
        today = fields.Date.today()
        rows = []
        for line in lines:
            exp = self._wms_line_expiry(line)
            left = (exp - today).days if exp else 0
            rows.append("- %s: %d day(s) of shelf life left" % (line.product_id.display_name, left))
        return (
            "Short-dated stock. These line(s) have less than %d days of shelf "
            "life — the minimum for receiving:\n%s\n\nA Manager must approve "
            "short-dated stock before it can be received." % (days, "\n".join(rows))
        )

    def action_receive_short_dated_override(self):
        """V20-018 — Manager-only: accept short-dated stock and validate."""
        self.ensure_one()
        if not self.env.user.has_group("wms_location.group_wms_manager"):
            raise UserError("Only a Manager can accept short-dated stock.")
        return self.with_context(wms_allow_short_dated=True).action_validate()

    @api.model
    def _wms_find_or_create_lot(self, line):
        """Find an existing lot for (product, batch) in this company, or create a
        new one — NEVER merge two distinct batches. Auto-names when no batch."""
        Lot = self.env["stock.lot"]
        product = line.product_id
        batch = (line.wms_batch or "").strip()
        expiry = line.wms_expiry or product.product_tmpl_id.wms_expiry_date
        if batch:
            existing = Lot.search(
                [
                    ("product_id", "=", product.id),
                    ("name", "=", batch),
                    ("company_id", "in", [self.env.company.id, False]),
                ],
                limit=1,
            )
            if existing:
                # Same batch already on file → add to the existing lot (never a
                # silent duplicate). Backfill metadata if it was blank.
                self._wms_backfill_lot_meta(existing, line, expiry)
                return existing
            name = batch
        else:
            name = self.env["ir.sequence"].next_by_code("wms.lot.auto") or (
                "LOT-%s" % (product.default_code or product.id)
            )
        vals = {
            "name": name,
            "product_id": product.id,
            "company_id": self.env.company.id,
        }
        if expiry:
            vals["expiration_date"] = fields.Datetime.to_datetime(expiry)
        if line.wms_supplier_id:
            vals["wms_supplier_id"] = line.wms_supplier_id.id
        return Lot.create(vals)

    @api.model
    def _wms_backfill_lot_meta(self, lot, line, expiry):
        """Fill expiry / supplier on an existing lot only when currently blank —
        never overwrite an established batch's metadata."""
        vals = {}
        if expiry and not lot.expiration_date:
            vals["expiration_date"] = fields.Datetime.to_datetime(expiry)
        if line.wms_supplier_id and not lot.wms_supplier_id:
            vals["wms_supplier_id"] = line.wms_supplier_id.id
        if vals:
            lot.write(vals)

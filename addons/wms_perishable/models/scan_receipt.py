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
        # V20-005: ensure every lot-tracked line carries a lot BEFORE the v19
        # validate runs (its lot-carrying loop then lands the lot on the move
        # line). Idempotent — lines that already have a lot are left alone, so a
        # double-submit re-entry is a no-op here too.
        for line in self.line_ids:
            if line.product_id.tracking == "lot" and not line.lot_id:
                line.lot_id = self._wms_find_or_create_lot(line)
        return super().action_validate()

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

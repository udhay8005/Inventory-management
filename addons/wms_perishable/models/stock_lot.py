"""V20-007 — extend stock.lot with the perishable lifecycle + supplier/expiry
metadata (data model only; the UI surfacing lives with the lot views/timeline,
V20-017). Additive _inherit — no v19 file edited, no flow changed.

Field contract is the frozen spec, docs/v20-perishable-engine/03-database-and-migration.md
(`stock.lot` table). `expiration_date` / `use_date` already come from the
product_expiry dependency; this adds the lifecycle state, supplier traceability,
manufacture date, and a computed expired flag.
"""

from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    wms_lot_state = fields.Selection(
        [
            ("available", "Available"),
            ("quarantine", "Quarantine"),
            ("recalled", "Recalled"),
            ("destroyed", "Destroyed"),
        ],
        string="Lot state",
        default="available",
        required=True,
        index=True,
        help="Lifecycle state of this lot. 'available' is normal; quarantine / "
        "recalled / destroyed lots are excluded from FEFO issuing (wired in the "
        "recall/quarantine tickets, V20-013/014). Distinct from native "
        "reservation and from the computed expired flag.",
    )
    wms_supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        help="Supplier this batch was received from — for recall and traceability.",
    )
    wms_supplier_batch = fields.Char(
        string="Supplier batch",
        help="The supplier's own batch / lot code, when it differs from our lot name.",
    )
    wms_supplier_invoice = fields.Char(
        string="Supplier invoice",
        help="Inbound invoice / delivery reference, for traceability.",
    )
    wms_manufacture_date = fields.Date(
        string="Manufacture date",
        help="Optional manufacture date of this batch.",
    )
    wms_is_expired = fields.Boolean(
        string="Expired",
        compute="_compute_wms_is_expired",
        help="True when this lot's expiration date is in the past. Computed from "
        "product_expiry's expiration_date; not stored.",
    )

    @api.depends("expiration_date")
    def _compute_wms_is_expired(self):
        now = fields.Datetime.now()
        for lot in self:
            lot.wms_is_expired = bool(lot.expiration_date and lot.expiration_date < now)

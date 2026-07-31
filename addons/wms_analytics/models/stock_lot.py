"""Wave 2 #10 — Lot Audit / Completeness Score.

Scores how complete a lot's traceability metadata is, out of seven checks
(batch, supplier, barcode, expiry, timeline, movement, storage). Surfaced as a
badge on the lot form and a sortable column so keepers can find under-documented
lots. Non-stored compute (always fresh): the activity checks read live quants /
move lines, so a stored value would go stale.
"""

from odoo import api, fields, models

AUDIT_CHECKS = ("batch", "supplier", "barcode", "expiry", "timeline", "movement", "storage")


class StockLot(models.Model):
    _inherit = "stock.lot"

    wms_audit_batch_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_supplier_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_barcode_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_expiry_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_timeline_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_movement_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_storage_ok = fields.Boolean(compute="_compute_wms_audit_score")
    wms_audit_score = fields.Integer(
        string="Audit score",
        compute="_compute_wms_audit_score",
        help="Traceability completeness, 0-7: batch, supplier, barcode, expiry, "
        "timeline, movement, storage.",
    )
    wms_audit_pct = fields.Float(
        string="Audit %",
        compute="_compute_wms_audit_score",
        help="Audit score as a percentage of the 7 checks.",
    )
    wms_audit_band = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        string="Audit band",
        compute="_compute_wms_audit_score",
        help="HIGH = 6-7 checks pass, MEDIUM = 4-5, LOW = 0-3.",
    )

    @api.depends(
        "name",
        "wms_supplier_id",
        "expiration_date",
        "wms_manufacture_date",
        "wms_movement_count",
    )
    def _compute_wms_audit_score(self):
        Quant = self.env["stock.quant"]
        live = (
            Quant.search([("lot_id", "in", self.ids), ("quantity", ">", 0)])
            if self.ids
            else Quant.browse()
        )
        by_lot = {}
        for q in live:
            by_lot.setdefault(q.lot_id.id, self.env["stock.quant"])
            by_lot[q.lot_id.id] |= q
        for lot in self:
            quants = by_lot.get(lot.id, Quant.browse())
            name = lot.name or ""
            batch_ok = bool(name) and not name.startswith("LOT-")
            supplier_ok = bool(lot.wms_supplier_id)
            barcode_ok = bool(name)
            expiry_ok = bool(lot.expiration_date)
            timeline_ok = (lot.wms_movement_count or 0) > 0
            movement_ok = bool(quants)
            storage_ok = any(
                q.location_id.usage == "internal"
                and not q.location_id.wms_is_damage
                and not q.location_id.wms_is_repair
                for q in quants
            )
            lot.wms_audit_batch_ok = batch_ok
            lot.wms_audit_supplier_ok = supplier_ok
            lot.wms_audit_barcode_ok = barcode_ok
            lot.wms_audit_expiry_ok = expiry_ok
            lot.wms_audit_timeline_ok = timeline_ok
            lot.wms_audit_movement_ok = movement_ok
            lot.wms_audit_storage_ok = storage_ok
            score = sum(
                (
                    batch_ok,
                    supplier_ok,
                    barcode_ok,
                    expiry_ok,
                    timeline_ok,
                    movement_ok,
                    storage_ok,
                )
            )
            lot.wms_audit_score = score
            lot.wms_audit_pct = round(100.0 * score / len(AUDIT_CHECKS), 1)
            lot.wms_audit_band = "high" if score >= 6 else "medium" if score >= 4 else "low"

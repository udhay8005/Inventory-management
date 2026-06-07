"""Inherit stock.move.line to snapshot unit cost at validate-time.

FPAT High: the Consumption Value report previously joined to
product.product.standard_price LIVE, so a cost change in 2026 retroactively
rewrote 2025's consumption totals. Trustees lost confidence in the figures.
This module attaches a `wms_unit_cost_at_done` snapshot to every move line at
the moment the validate-time chatter is posted, so historic value is fixed.
"""

from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    wms_unit_cost_at_done = fields.Float(
        string="Unit cost at done",
        readonly=True,
        copy=False,
        help="Per-unit cost captured at the moment this Scan Issue / Scan "
        "Receipt move line was validated. The Consumption Value report reads "
        "this column instead of joining to product.standard_price, so a later "
        "cost change does not rewrite historical value. NULL on legacy rows; "
        "the view falls back to current cost in that case.",
    )

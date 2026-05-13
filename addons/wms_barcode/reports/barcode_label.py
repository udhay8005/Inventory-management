"""Helpers used by the QWeb report template to render Code128 barcodes.

We rely on Odoo's existing IrActionsReport `barcode` widget (it renders SVG
inside the PDF), so no extra image bytes need to be generated here. This
module exists so the manifest's "depends" graph has a clear extension point;
add custom label sizes / batched printing here.
"""
from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"
    # placeholder for future overrides (e.g. custom paperformat per template)

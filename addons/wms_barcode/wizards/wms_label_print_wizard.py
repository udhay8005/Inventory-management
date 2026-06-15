# -*- coding: utf-8 -*-
"""One-click direct label printing wizard.

Opened from the Action menu of the Products list and the Slots / Racks /
Compartments lists (and a single record's form). Staff select one or many
records, choose the printer + copies, press Print, and the labels come straight
out of the thermal printer — no browser print dialog, no PDF download.

It delegates the actual TSPL build + send to ``wms.label.printer`` so products
and locations share one print path.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Models this wizard knows how to turn into labels, with the field map.
_SUPPORTED = {
    "product.product": "products",
    "stock.location": "locations",
}


class WmsLabelPrintWizard(models.TransientModel):
    _name = "wms.label.print.wizard"
    _description = "Print Labels (direct to printer)"

    printer_id = fields.Many2one(
        "wms.label.printer",
        string="Printer",
        required=True,
        default=lambda self: self.env["wms.label.printer"].get_default_printer(),
        help="Where to send the labels. Managers set these up in "
        "Configuration → Label Printers.",
    )
    copies = fields.Integer(
        default=1,
        required=True,
        help="How many copies of EACH selected label to print.",
    )
    record_count = fields.Integer(string="Selected", readonly=True)
    summary = fields.Char(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        model = self.env.context.get("active_model")
        ids = self.env.context.get("active_ids") or []
        if model not in _SUPPORTED:
            raise UserError(
                _(
                    "Label printing isn't available for this screen. Use it from the "
                    "Products list or the Slots / Racks / Compartments lists."
                )
            )
        res["record_count"] = len(ids)
        res["summary"] = _("%(n)s %(kind)s selected") % {
            "n": len(ids),
            "kind": _SUPPORTED[model],
        }
        return res

    def _labels_for(self, model, ids):
        """Build the list of {title, subtitle, barcode} dicts for the records."""
        records = self.env[model].browse(ids).exists()
        labels, skipped = [], []
        if model == "product.product":
            for p in records:
                code = p.barcode or p.default_code
                if not code:
                    skipped.append(p.display_name)
                    continue
                labels.append(
                    {
                        "title": p.default_code or p.name,
                        "subtitle": p.name,
                        "barcode": p.barcode or p.default_code,
                    }
                )
        else:  # stock.location
            for loc in records:
                if not loc.barcode:
                    skipped.append(loc.display_name)
                    continue
                labels.append(
                    {
                        "title": loc.barcode,
                        "subtitle": loc.name or loc.complete_name,
                        "barcode": loc.barcode,
                    }
                )
        return labels, skipped

    def action_print(self):
        self.ensure_one()
        if self.copies < 1:
            raise UserError(_("Copies must be at least 1."))
        model = self.env.context.get("active_model")
        ids = self.env.context.get("active_ids") or []
        if model not in _SUPPORTED or not ids:
            raise UserError(_("Nothing selected to print."))
        labels, skipped = self._labels_for(model, ids)
        if not labels:
            raise UserError(
                _(
                    "None of the selected records has a barcode to print.\nSet a "
                    "barcode on them first (Configuration → Onboard Products, or the "
                    "location form)."
                )
            )
        printed = self.printer_id.print_labels(labels, copies=self.copies)
        # printed is the TSPL string in dry-run mode (tests); a count otherwise.
        n_labels = len(labels) if not isinstance(printed, int) else printed
        msg = _("Sent %(n)s label(s) ×%(c)s to %(printer)s.") % {
            "n": n_labels,
            "c": self.copies,
            "printer": self.printer_id.name,
        }
        if skipped:
            msg += _("\nSkipped %(s)s with no barcode.") % {"s": len(skipped)}
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Labels sent to printer"),
                "message": msg,
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

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
# product.template is supported because the WMS "Products" list is the template
# (F1 fix); each template resolves to its single variant for the barcode.
_SUPPORTED = {
    "product.product": "products",
    "product.template": "products",
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

    # Friendly names for the WMS location types (shown on the label sub-line).
    _LOC_TYPE = {
        "zone": "Zone",
        "rack": "Rack",
        "compartment": "Compartment",
        "slot": "Slot",
        "floor": "Floor zone",
    }

    def _labels_for(self, model, ids):
        """Build the {title, subtitle, barcode} dicts for the records.

        Kept non-repetitive: the code shows on the title line + under the barcode
        (standard); the sub-line carries *context* (the parent path + type for a
        location; the SKU + unit for a product) without repeating the code."""
        records = self.env[model].browse(ids).exists()
        # A product.template resolves to its single variant (the flat one-variant
        # model) so products and templates share the same label-building code.
        if model == "product.template":
            records = records.product_variant_id
        labels, skipped = [], []
        if model in ("product.product", "product.template"):
            for p in records:
                code = p.barcode or p.default_code
                if not code:
                    skipped.append(p.display_name)
                    continue
                detail = "SKU: %s" % (p.default_code or "-")
                if p.uom_id:
                    detail += "  -  Unit: %s" % p.uom_id.name
                labels.append({"title": p.name, "subtitle": detail, "barcode": code})
        else:  # stock.location
            for loc in records:
                if not loc.barcode:
                    skipped.append(loc.display_name)
                    continue
                title = "%s  %s" % (loc.barcode, loc.name) if loc.name else loc.barcode
                parent = loc.location_id.complete_name or ""
                kind = self._LOC_TYPE.get(loc.wms_location_type, "Location")
                detail = ("%s  -  %s" % (parent, kind)) if parent else kind
                labels.append({"title": title, "subtitle": detail, "barcode": loc.barcode})
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

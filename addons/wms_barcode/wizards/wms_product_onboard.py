"""Bulk-onboard wizard: catalog + initial stock + labels in one screen.

The trust's daily workflow before this wizard:
  1. Inventory > Products > New, type the name, pick the kind,
     save (auto-generates SKU + Code128 + EAN-13).
  2. Operations > Scan Receipt, scan a slot, scan the product
     barcode, enter qty, validate.
  3. Re-open the product, Action > Print thermal label.

Three context switches per item, three save buttons. Painful for
a 200-row initial inventory load.

This wizard collapses all three into one editable table. Each row:
  - product name + WMS kind (drives auto-SKU + auto-barcode)
  - initial quantity (default 1)
  - slot location (dropdown OR scan the slot's barcode)

On submit:
  - product.template.create() runs (which already auto-fills SKU,
    Code128 barcode, and creates the EAN-13 wms.barcode.alias).
  - A stock.quant is placed in the chosen slot for the initial qty.
  - A combined thermal-label PDF opens with one label per row.

Same wizard, one row or two hundred. Paste-from-Excel into the
editable list works out of the box because Odoo's list view
supports clipboard import.
"""

from __future__ import annotations

from odoo import _, api, fields, models

# Re-use the canonical kind list so this wizard stays aligned with
# the source of truth in wms_location.
from odoo.addons.wms_location.models.product_template import WMS_KIND_SELECTION
from odoo.exceptions import UserError


class WmsProductOnboard(models.TransientModel):
    _name = "wms.product.onboard"
    _description = "Bulk onboard: catalog + stock + labels"

    line_ids = fields.One2many(
        "wms.product.onboard.line",
        "wizard_id",
        string="Products to onboard",
    )

    summary = fields.Char(readonly=True)

    # --------------------------------------------------------------
    # Main action
    # --------------------------------------------------------------
    def _validate(self):
        """Surface row-level problems BEFORE we start writing to the
        database, so a 50th-row typo doesn't leave 49 half-saved
        products behind."""
        if not self.line_ids:
            raise UserError(_("Add at least one product line before submitting."))
        for line in self.line_ids:
            if not line.name:
                raise UserError(_("Row %d: product name is required.") % (line._origin.id or 0))
            if not line.wms_product_kind:
                raise UserError(
                    _(
                        "Row %r: pick a WMS Kind so the system can choose the "
                        "right SKU prefix (TOOL-, CONS-, ...)."
                    )
                    % line.name
                )
            if line.initial_qty < 0:
                raise UserError(_("Row %r: initial quantity cannot be negative.") % line.name)
            # Allow qty=0 (catalog-only rows). If qty>0 we need a slot.
            if line.initial_qty > 0 and not line.location_id:
                raise UserError(
                    _(
                        "Row %r: pick a slot (or scan its barcode) when "
                        "initial quantity is > 0. Use 0 for catalog-only rows."
                    )
                    % line.name
                )
            # Medicine and Feed without expiry is a real liability.
            # Treat them like an audit-trail field on damage events:
            # block the save until the field is filled.
            if line.wms_product_kind in ("medicine", "feed") and not line.expiry_date:
                raise UserError(
                    _(
                        "Row %r is a %s product - the expiry date is "
                        "required. Enter the date stamped on the supplier's "
                        "label (or pack)."
                    )
                    % (
                        line.name,
                        dict(WMS_KIND_SELECTION).get(line.wms_product_kind, line.wms_product_kind),
                    )
                )

    def action_onboard(self):
        """Create products + place initial stock + open labels PDF."""
        self._validate()
        created_products = self._do_onboard()
        return self._labels_action(created_products)

    def action_onboard_no_print(self):
        """Create products + place initial stock. No PDF.

        Chain a `next: act_window_close` action so the dialog closes
        after the toast — without it the wizard sits in its post-save
        readonly state and an impatient double-click re-submits, which
        would silently create duplicate SKUs.
        """
        self._validate()
        created_products = self._do_onboard()
        n = len(created_products)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Onboarded"),
                "message": _(
                    "%d product%s created. Open Inventory -> WMS Products "
                    "to see the new SKUs. Print labels later via "
                    "Action -> Print thermal label."
                )
                % (n, "" if n == 1 else "s"),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _do_onboard(self):
        """Returns the recordset of newly-created product.product."""
        Product = self.env["product.product"]
        Template = self.env["product.template"]
        Quant = self.env["stock.quant"].sudo()

        created_variants = Product.browse()
        for line in self.line_ids:
            # 1. Create the template (auto-SKU + auto-Code128 + auto-EAN13
            #    happens inside product.template.create() override).
            # Odoo 19 collapsed the old 'product' (stockable) type
            # into 'consu' (Goods). All physical inventory uses
            # 'consu' now; the stockable/non-stockable split lives
            # on the boolean is_storable, which Odoo flips on for us
            # the moment we add a stock_quant.
            vals = {
                "name": line.name,
                "wms_product_kind": line.wms_product_kind,
                "type": "consu",
                "is_storable": True,
            }
            if line.list_price:
                vals["list_price"] = line.list_price
            # Hand the kind-specific extras to the template if the
            # Admin filled them on the wizard line.
            if line.expiry_date:
                vals["wms_expiry_date"] = line.expiry_date
            if line.batch_number:
                vals["wms_batch_number"] = line.batch_number
            if line.volume_litres:
                vals["wms_volume_litres"] = line.volume_litres
            tmpl = Template.create(vals)
            variant = tmpl.product_variant_ids[:1]
            created_variants |= variant

            # 2. Optional supplier
            if line.supplier_id:
                self.env["product.supplierinfo"].create(
                    {
                        "product_tmpl_id": tmpl.id,
                        "partner_id": line.supplier_id.id,
                    }
                )

            # 3. Place initial stock in the chosen slot.
            #    stock.quant create with sudo so the post-create
            #    fix-up (compute reserved_quantity etc.) bypasses
            #    the perm_unlink lockdown on quants for safety nets
            #    Odoo runs internally.
            if line.initial_qty > 0 and line.location_id:
                Quant.with_context(inventory_mode=True).create(
                    {
                        "product_id": variant.id,
                        "location_id": line.location_id.id,
                        "quantity": line.initial_qty,
                    }
                )

        self.summary = _("%d product%s onboarded with %d unit%s of stock placed.") % (
            len(self.line_ids),
            "" if len(self.line_ids) == 1 else "s",
            int(sum(self.line_ids.mapped("initial_qty"))),
            "" if int(sum(self.line_ids.mapped("initial_qty"))) == 1 else "s",
        )
        return created_variants

    # --------------------------------------------------------------
    # Combined labels PDF
    # --------------------------------------------------------------
    def _labels_action(self, products):
        """Return the action that opens the thermal-label report
        with all the newly-created products in one PDF.

        The existing report `wms_barcode.report_product_label_thermal`
        iterates `docs` over the recordset, so passing N product
        ids produces N labels in one file.
        """
        if not products:
            return {"type": "ir.actions.act_window_close"}
        return self.env.ref("wms_barcode.action_report_wms_product_label_thermal").report_action(
            products
        )


class WmsProductOnboardLine(models.TransientModel):
    _name = "wms.product.onboard.line"
    _description = "One row in the bulk-onboard wizard"

    wizard_id = fields.Many2one(
        "wms.product.onboard",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Product name", required=True)
    wms_product_kind = fields.Selection(
        WMS_KIND_SELECTION,
        string="WMS Kind",
        required=True,
        help="Drives the SKU prefix (TOOL-, CONS-, SPARE-, ...).",
    )
    initial_qty = fields.Float(
        string="Initial qty",
        default=1.0,
        help="Units to place in the slot below right after the "
        "product is created. Set to 0 for catalog-only entries.",
    )
    # Conditional fields surfaced in the editable list when the kind
    # is one of the perishable / detail-sensitive categories. They
    # write through to the matching product.template field on create.
    expiry_date = fields.Date(
        string="Expiry",
        help="Required for Medicine / Feed; useful for Fluid (oil "
        "going rancid) and Pooja (ghee). The Expiry Alert report "
        "uses this date.",
    )
    batch_number = fields.Char(
        string="Batch / lot",
        help="Supplier batch reference for medicine / feed traceability.",
    )
    volume_litres = fields.Float(
        string="Volume (L)",
        help="For fluid products: volume of one unit in litres.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Slot",
        domain="[('usage', '=', 'internal'), " "('wms_location_type', 'in', ('slot', 'floor'))]",
        help="Where the initial stock goes. Required when initial qty > 0.",
    )
    location_scan = fields.Char(
        string="Scan slot barcode",
        help="Scan a slot's barcode (e.g. R01-SH01-C01-SL01). "
        "The system auto-fills the Slot field on the left.",
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Default supplier (optional)",
        domain=[("supplier_rank", ">", 0)],
    )
    list_price = fields.Float(string="Unit price (optional)")

    @api.onchange("location_scan")
    def _onchange_location_scan(self):
        """Look up the scanned barcode against stock.location and
        auto-fill the slot dropdown. Clear the scan field so the
        next scan doesn't trip on stale text."""
        if not self.location_scan:
            return
        code = self.location_scan.strip()
        loc = self.env["stock.location"].search(
            [("barcode", "=", code), ("usage", "=", "internal")],
            limit=1,
        )
        if loc:
            self.location_id = loc.id
            self.location_scan = False
        else:
            return {
                "warning": {
                    "title": _("Slot not found"),
                    "message": _(
                        "No internal location matches barcode %r. Check "
                        "the slot sticker, or pick from the dropdown."
                    )
                    % code,
                }
            }

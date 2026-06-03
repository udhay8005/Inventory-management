import base64

from odoo import api, fields, models


class WmsLabelConfig(models.Model):
    """Admin-configurable layout for thermal sticker labels.

    The trust's printer takes a 4" x 2" (~101.6 x 50.8 mm) DIE-CUT roll at
    203 DPI, with a gap between stickers. Stickers leave the head with a
    fixed paper size; the only thing that varies between sites is where the
    barcode sits on the label, how big the logo is, and what extra text the
    trust wants next to it.

    All sizes here are millimetres so the form is readable; the report
    template just stamps them as CSS `mm` values. Use 0 to hide an element
    entirely.

    One row per company is enough -- `get_active()` resolves the one to use
    at print time. If no row exists, the defaults below are used as-is, so
    the report still works on a fresh install.
    """

    _name = "wms.label.config"
    _description = "Thermal label layout settings"

    name = fields.Char(
        string="Profile",
        default="Default thermal label",
        required=True,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        default=lambda s: s.env.company,
        required=True,
    )

    # ---- Paper -----------------------------------------------------------
    # Defaults tuned to the trust's actual hardware:
    #   * Sticker: 4 x 2 inch (101.6 x 50.8 mm) DIE-CUT label with a gap
    #     between stickers (gap_mm below).
    #   * Printer: TSC TE244, 203 DPI, USB, media = GAP. The driver writes
    #     a 101.6 x 50.8 mm PDF page -> printer rasters 1:1 onto one sticker
    #     and the gap sensor advances across the gap to the next.
    paper_width_mm = fields.Float(
        string="Label width (mm)",
        default=101.6,
        help="Label width. 101.6 mm = 4 inch, the die-cut sticker width. "
        "Change here if you switch to a different roll.",
    )
    paper_height_mm = fields.Float(
        string="Label height (mm)",
        default=50.8,
        help="Label height. 50.8 mm = 2 inch, the die-cut sticker height.",
    )
    gap_mm = fields.Float(
        string="Gap between labels (mm)",
        default=3.0,
        help="Physical gap between die-cut labels on the roll. Use it to "
        "calibrate the printer's gap sensor (TSC TE244: media = GAP). It "
        "does not change the printed area -- the page is exactly one label.",
    )

    # Default layout for the 101.6 x 50.8 mm (4 x 2 in) sticker:
    #   * Title (name) across the top, SKU on the second line.
    #   * A large Code128 barcode filling the lower half (easy to scan).
    #   * Optional logo tucked into the top-right corner.
    # Admin can move any element on the Label Settings form.

    # ---- Logo block (top-right corner) -----------------------------------
    logo = fields.Binary(
        string="Logo",
        attachment=True,
        help="Optional. Upload a PNG / JPG to print in the top-right corner "
        "of the label. Leave empty to hide it.",
    )
    logo_x_mm = fields.Float(string="Logo left (mm)", default=79.0)
    logo_y_mm = fields.Float(string="Logo top (mm)", default=2.0)
    logo_width_mm = fields.Float(string="Logo width (mm)", default=20.0)
    logo_height_mm = fields.Float(string="Logo height (mm)", default=11.0)

    # ---- Title text (top line, across the label) -------------------------
    show_title = fields.Boolean(string="Show product / location name", default=True)
    title_x_mm = fields.Float(string="Title left (mm)", default=3.0)
    title_y_mm = fields.Float(string="Title top (mm)", default=3.0)
    title_width_mm = fields.Float(string="Title width (mm)", default=73.0)
    title_size_pt = fields.Float(string="Title font size (pt)", default=13.0)
    title_bold = fields.Boolean(string="Title bold", default=True)

    # ---- SKU / sub-line (second line) ------------------------------------
    show_subtitle = fields.Boolean(string="Show SKU / sub-line", default=True)
    subtitle_x_mm = fields.Float(string="Sub-line left (mm)", default=3.0)
    subtitle_y_mm = fields.Float(string="Sub-line top (mm)", default=15.0)
    subtitle_width_mm = fields.Float(string="Sub-line width (mm)", default=73.0)
    subtitle_size_pt = fields.Float(string="Sub-line font size (pt)", default=10.0)

    # ---- Barcode block (lower half, full width) --------------------------
    # At 203 DPI / 90 mm we have ~719 dots horizontally -- plenty for a
    # Code128 SKU (e.g. MED-00005) or an EAN-13. The taller 18 mm bars on
    # the 2-inch label scan easily. The Helett HT20pro reads 1D + 2D so QR
    # future-expansion works in the same block.
    barcode_x_mm = fields.Float(string="Barcode left (mm)", default=6.0)
    barcode_y_mm = fields.Float(string="Barcode top (mm)", default=26.0)
    barcode_width_mm = fields.Float(string="Barcode width (mm)", default=90.0)
    barcode_height_mm = fields.Float(string="Barcode height (mm)", default=18.0)
    show_human_readable = fields.Boolean(
        string="Show the number below the bars",
        default=True,
    )
    human_readable_size_pt = fields.Float(
        string="Number font size (pt)",
        default=8.0,
    )

    @api.model
    def get_active(self):
        """Return the active label config to use for the current company,
        or a fresh in-memory record carrying the defaults if none exist
        yet. Always returns a single record."""
        config = self.search(
            [
                ("active", "=", True),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        return config or self.new({})

    @api.model
    def barcode_data_uri(self, value, width=760, height=160):
        """Render a Code128 barcode as a base64 data URI suitable for
        embedding directly into an <img src> in a QWeb report.

        wkhtmltopdf can't reach the live `/report/barcode/` URL during PDF
        generation (no DB context inside the subprocess), so we skip the
        HTTP round-trip and inline the PNG bytes instead.
        """
        if not value:
            return ""
        png_bytes = self.env["ir.actions.report"].barcode(
            "Code128", value, width=width, height=height, humanreadable=0
        )
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return "data:image/png;base64," + b64

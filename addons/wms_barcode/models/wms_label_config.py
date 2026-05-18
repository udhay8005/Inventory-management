import base64

from odoo import api, fields, models


class WmsLabelConfig(models.Model):
    """Admin-configurable layout for thermal sticker labels.

    The printer most trusts use takes a 4" × 1" roll (≈ 102 × 25 mm) at
    203 DPI. Stickers leave the head with a fixed paper size; the only
    thing that varies between sites is where the barcode sits on the
    label, how big the logo is, and what extra text the trust wants
    next to it.

    All sizes here are millimetres so the form is readable; the report
    template just stamps them as CSS `mm` values. Use 0 to hide an
    element entirely.

    One row per company is enough — `ensure_singleton()` resolves the
    one to use at print time. If no row exists, the defaults below are
    used as-is, so the report still works on a fresh install.
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
    paper_width_mm = fields.Float(
        string="Label width (mm)",
        default=102.0,
        help="Roll width. 102 mm = 4 inches, which fits the trust's " "thermal printer.",
    )
    paper_height_mm = fields.Float(
        string="Label height (mm)",
        default=25.0,
        help="Sticker height. 25 mm = 1 inch.",
    )

    # ---- Barcode block ---------------------------------------------------
    barcode_x_mm = fields.Float(string="Barcode left (mm)", default=50.0)
    barcode_y_mm = fields.Float(string="Barcode top (mm)", default=4.0)
    barcode_width_mm = fields.Float(string="Barcode width (mm)", default=50.0)
    barcode_height_mm = fields.Float(string="Barcode height (mm)", default=13.0)
    show_human_readable = fields.Boolean(
        string="Show the number below the bars",
        default=True,
    )
    human_readable_size_pt = fields.Float(
        string="Number font size (pt)",
        default=7.0,
    )

    # ---- Logo block ------------------------------------------------------
    logo = fields.Binary(
        string="Logo",
        attachment=True,
        help="Optional. Upload a PNG / JPG to print to the left of the "
        "barcode. Leave empty to hide the logo space.",
    )
    logo_x_mm = fields.Float(string="Logo left (mm)", default=2.0)
    logo_y_mm = fields.Float(string="Logo top (mm)", default=2.0)
    logo_width_mm = fields.Float(string="Logo width (mm)", default=18.0)
    logo_height_mm = fields.Float(string="Logo height (mm)", default=18.0)

    # ---- Title text ------------------------------------------------------
    show_title = fields.Boolean(string="Show product / location name", default=True)
    title_x_mm = fields.Float(string="Title left (mm)", default=22.0)
    title_y_mm = fields.Float(string="Title top (mm)", default=2.0)
    title_width_mm = fields.Float(string="Title width (mm)", default=78.0)
    title_size_pt = fields.Float(string="Title font size (pt)", default=10.0)
    title_bold = fields.Boolean(string="Title bold", default=True)

    # ---- SKU / sub-line --------------------------------------------------
    show_subtitle = fields.Boolean(string="Show SKU / sub-line", default=True)
    subtitle_x_mm = fields.Float(string="Sub-line left (mm)", default=22.0)
    subtitle_y_mm = fields.Float(string="Sub-line top (mm)", default=8.0)
    subtitle_width_mm = fields.Float(string="Sub-line width (mm)", default=78.0)
    subtitle_size_pt = fields.Float(string="Sub-line font size (pt)", default=7.0)

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
    def barcode_data_uri(self, value, width=600, height=120):
        """Render a Code128 barcode as a base64 data URI suitable for
        embedding directly into an <img src> in a QWeb report.

        wkhtmltopdf can't reach the live `/report/barcode/` URL during
        PDF generation (no DB context inside the subprocess), so we
        skip the HTTP round-trip and inline the PNG bytes instead.
        """
        if not value:
            return ""
        png_bytes = self.env["ir.actions.report"].barcode(
            "Code128", value, width=width, height=height, humanreadable=0
        )
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return "data:image/png;base64," + b64

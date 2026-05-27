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
    # Defaults tuned to the trust's actual hardware:
    #   * Sticker: True-Ally 100 × 25 mm direct-thermal roll
    #     (Amazon ASIN B0B1BCP14Z, 1000 labels / roll).
    #   * Printer: TSC TE244, 203 DPI, USB. Driver writes a 100×25 mm
    #     PDF page → printer rasters 1:1 onto the sticker.
    # The earlier 102 mm default was a 4-inch approximation but the
    # actual sticker is exactly 100 mm — anything wider clips at the
    # right edge or mis-feeds onto the next sticker.
    paper_width_mm = fields.Float(
        string="Label width (mm)",
        default=100.0,
        help="Roll width. 100 mm matches the True-Ally 100×25 sticker "
        "the trust uses. Change here if you switch to a different roll.",
    )
    paper_height_mm = fields.Float(
        string="Label height (mm)",
        default=25.0,
        help="Sticker height. 25 mm matches the True-Ally 100×25 sticker.",
    )

    # Default layout — the 1 inch logo + 3 inch right-block split.
    #
    # Sticker is 100 × 25 mm. The left ~24 mm holds the logo; the right
    # 74 mm holds the title, the SKU / sub-line, and the barcode stacked
    # vertically. The right block starts at x = 26 mm so 26 + 74 = 100 mm
    # exactly — every pixel of the sticker is used and nothing clips off
    # the right edge. Admin can change any of these on the Label
    # Settings form.

    # ---- Logo block (LEFT ~1 inch) ---------------------------------------
    logo = fields.Binary(
        string="Logo",
        attachment=True,
        help="Optional. Upload a PNG / JPG to print on the left side of "
        "the label (the ~1 inch logo zone). Leave empty to hide it.",
    )
    logo_x_mm = fields.Float(string="Logo left (mm)", default=1.0)
    logo_y_mm = fields.Float(string="Logo top (mm)", default=1.0)
    logo_width_mm = fields.Float(string="Logo width (mm)", default=23.0)
    logo_height_mm = fields.Float(string="Logo height (mm)", default=23.0)

    # ---- Title text (RIGHT ~3 inch, top line) ----------------------------
    show_title = fields.Boolean(string="Show product / location name", default=True)
    title_x_mm = fields.Float(string="Title left (mm)", default=26.0)
    title_y_mm = fields.Float(string="Title top (mm)", default=1.0)
    title_width_mm = fields.Float(string="Title width (mm)", default=74.0)
    title_size_pt = fields.Float(string="Title font size (pt)", default=9.0)
    title_bold = fields.Boolean(string="Title bold", default=True)

    # ---- SKU / sub-line (RIGHT ~3 inch, second line) ---------------------
    show_subtitle = fields.Boolean(string="Show SKU / sub-line", default=True)
    subtitle_x_mm = fields.Float(string="Sub-line left (mm)", default=26.0)
    subtitle_y_mm = fields.Float(string="Sub-line top (mm)", default=5.0)
    subtitle_width_mm = fields.Float(string="Sub-line width (mm)", default=74.0)
    subtitle_size_pt = fields.Float(string="Sub-line font size (pt)", default=7.0)

    # ---- Barcode block (RIGHT ~3 inch, bottom) ---------------------------
    # At 203 DPI / 74 mm we have ~590 dots horizontally — plenty for a
    # Code128 SKU (e.g. MED-00005 is ~22 modules, prints at ~13 mm) or
    # an EAN-13 (109 modules, ~36 mm at default X-dim). The Helett
    # HT20pro scanner reads both 1D + 2D so QR future-expansion works
    # in the same block.
    barcode_x_mm = fields.Float(string="Barcode left (mm)", default=26.0)
    barcode_y_mm = fields.Float(string="Barcode top (mm)", default=9.0)
    barcode_width_mm = fields.Float(string="Barcode width (mm)", default=74.0)
    barcode_height_mm = fields.Float(string="Barcode height (mm)", default=12.0)
    show_human_readable = fields.Boolean(
        string="Show the number below the bars",
        default=True,
    )
    human_readable_size_pt = fields.Float(
        string="Number font size (pt)",
        default=6.0,
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

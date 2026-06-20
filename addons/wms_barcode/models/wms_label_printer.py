# -*- coding: utf-8 -*-
"""Direct-to-printer label printing for TSPL thermal printers (TSC TE244).

Why this exists
---------------
The WMS server runs natively on the SAME Windows PC as the label printer, so it
can push the printer's native **TSPL** language straight to the Windows print
spooler (RAW datatype) — no browser print dialog, no PDF download, no QZ Tray /
WebUSB / extra agent. Because TSPL carries the label SIZE itself (``SIZE`` /
``GAP``), the output is always exact-size and upright; it can't be shrunk or
rotated by a browser the way the PDF path could.

A ``wms.label.printer`` record is a reusable printer profile (which spooler
printer, media size, darkness, alignment nudge). The print wizard
(``wms.label.print.wizard``) builds one label per selected product / location
and sends them here.

Portability
-----------
``win32print`` is imported lazily inside :meth:`send_raw` so the module still
loads + tests run on Linux CI (where pywin32 is absent). Network (raw 9100)
printers work on any OS via a plain socket. Pass ``wms_print_dry_run`` in the
context to build the TSPL without sending (used by the tests and previews).
"""

import logging
import socket

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# A Code128 narrow-bar must stay >= ~0.25 mm (2 dots @203 dpi) to scan reliably.
_MIN_NARROW_DOTS = 2


def _ascii(text):
    """TSPL built-in fonts are ASCII; drop the rest and the quote that would
    terminate a TSPL string literal."""
    return (text or "").replace('"', "'").encode("ascii", "ignore").decode("ascii")


class WmsLabelPrinter(models.Model):
    _name = "wms.label.printer"
    _description = "Label Printer (direct TSPL)"
    _order = "is_default desc, name"

    name = fields.Char(
        required=True,
        help="Friendly name shown to staff, e.g. 'Thermal label printer'.",
    )
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string="Default printer",
        help="The printer pre-selected when staff print labels. Only one can be " "the default.",
    )
    connection = fields.Selection(
        [("spooler", "Windows printer (USB / local)"), ("network", "Network (IP)")],
        default="spooler",
        required=True,
        help="USB / local: the printer installed on this PC (sent via the Windows "
        "spooler). Network: a printer with its own IP address (raw port 9100).",
    )
    system_name = fields.Char(
        string="Windows printer name",
        help="Exact name as it appears in Windows 'Printers & scanners' "
        "(e.g. 'TSC TE244'). Used for USB / local printers.",
    )
    host = fields.Char(string="IP address", help="Network printer IP, e.g. 192.168.0.50.")
    port = fields.Integer(string="Port", default=9100)

    # --- media + quality (TSPL) ------------------------------------------
    label_width_mm = fields.Float(string="Label width (mm)", default=100.0, required=True)
    label_height_mm = fields.Float(string="Label height (mm)", default=25.0, required=True)
    gap_mm = fields.Float(
        string="Gap between labels (mm)",
        default=3.0,
        help="The die-cut gap height. Sent in every job so the printer lands one "
        "label per print.",
    )
    dpi = fields.Integer(default=203, required=True, help="TSC TE244 is 203 dpi.")
    density = fields.Integer(
        default=10,
        help="Darkness 0-15. Raise if the print is too light, lower if it smudges.",
    )
    speed = fields.Integer(default=3, help="Print speed in inches/sec (TE244: 2-6).")
    x_offset_mm = fields.Float(
        string="Shift right (mm)",
        default=2.0,
        help="Nudge everything right. Use with 'Shift down' to align the print "
        "inside the sticker.",
    )
    y_offset_mm = fields.Float(string="Shift down (mm)", default=1.5)
    brand_line = fields.Char(
        string="Brand line",
        default="Mercy & Care For Cows Dakshin Vrindavan PCT",
        help="Small heading printed on every label (the trust's name). Clear it " "to hide.",
    )
    notes = fields.Text()

    # ---------------------------------------------------------------------
    # constraints
    # ---------------------------------------------------------------------
    @api.constrains("label_width_mm", "label_height_mm")
    def _check_media(self):
        for p in self:
            if p.label_width_mm <= 0 or p.label_height_mm <= 0:
                raise ValidationError(_("Label width and height must be greater than 0."))

    @api.constrains("connection", "system_name", "host")
    def _check_target(self):
        for p in self:
            if p.connection == "spooler" and not p.system_name:
                raise ValidationError(_("A USB / local printer needs the Windows printer name."))
            if p.connection == "network" and not p.host:
                raise ValidationError(_("A network printer needs an IP address."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._enforce_single_default()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_default"):
            self._enforce_single_default()
        return res

    def _enforce_single_default(self):
        """Keep at most one default printer."""
        default = self.filtered("is_default")
        if default:
            (self.search([("is_default", "=", True)]) - default[0]).write({"is_default": False})

    # ---------------------------------------------------------------------
    # helpers
    # ---------------------------------------------------------------------
    @api.model
    def get_default_printer(self):
        """The default printer, else the first active one, else False."""
        return self.search([("is_default", "=", True)], limit=1) or self.search([], limit=1)

    def _dots(self, mm):
        """Millimetres -> printer dots at this printer's DPI."""
        return int(round((mm or 0.0) * (self.dpi or 203) / 25.4))

    @api.model
    def list_system_printers(self):
        """Names of printers installed on the server (Windows). [] elsewhere."""
        try:
            import win32print
        except ImportError:
            return []
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted({p[2] for p in win32print.EnumPrinters(flags)})

    # ---------------------------------------------------------------------
    # TSPL generation
    # ---------------------------------------------------------------------
    _CODE39_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%"

    def _barcode_params(self, code, x_left, x_right):
        """Pick symbology + module width + a centred x so the barcode fills the
        right zone. Short, Code39-compatible codes use **Code 39** (more bars =
        a fuller, normal-looking barcode); everything else uses the compact
        **Code 128**. The encoded value is never altered, so scanning is
        unaffected."""
        avail = max(1, x_right - x_left)
        c39 = set(self._CODE39_CHARS)
        if code and len(code) <= 8 and code == code.upper() and all(ch in c39 for ch in code):
            sym, modules, cap = "39", 13 * (len(code) + 2), 5
        else:
            sym, modules, cap = "128", 11 * (len(code) + 2) + 13, 4
        narrow = max(_MIN_NARROW_DOTS, min(cap, int(0.80 * avail / max(modules, 1))))
        bx = x_left + max(0, (avail - modules * narrow) // 2)
        return sym, narrow, narrow * 2, bx

    def _logo_bytes(self, x, y, box_w, box_h):
        """Render the trust logo as a 1-bit TSPL BITMAP for the left zone.

        Uses the admin-uploaded logo (``wms.label.config.logo``) if set, else
        the packaged cow image. The image is dithered to black/white — dark
        areas print, light areas stay blank — and centred in the box.
        Best-effort: any failure just prints the label without the logo."""
        import base64
        import io
        import os

        raw = None
        cfg = self.env["wms.label.config"].sudo().get_active()
        if cfg and cfg.logo:
            raw = base64.b64decode(cfg.logo)
        else:
            path = os.path.join(os.path.dirname(__file__), "..", "static", "img", "label_logo.png")
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    raw = fh.read()
        if not raw or box_w < 8 or box_h < 8:
            return b""
        try:
            from PIL import Image, ImageOps

            img = Image.open(io.BytesIO(raw))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
                flat.alpha_composite(img)
                img = flat.convert("RGB")
            grey = ImageOps.autocontrast(ImageOps.grayscale(img))
            grey.thumbnail((int(box_w), int(box_h)))
            one = grey.convert("1")  # 1 = white, 0 = black (PIL)
            data = one.point(lambda p: 0 if p else 255).tobytes()  # dark -> printed
            w, h = one.size
            cx = x + max(0, (box_w - w) // 2)
            cy = y + max(0, (box_h - h) // 2)
            return ("BITMAP %d,%d,%d,%d,0," % (cx, cy, (w + 7) // 8, h)).encode("ascii") + data
        except Exception:  # noqa: BLE001 - never let a logo break a print run
            _logger.exception("label logo render failed; printing without it")
            return b""

    @staticmethod
    def _assert_printable_barcode(barcode):
        """Reject a barcode the thermal printer's ASCII symbology cannot reproduce.

        TSPL built-in barcode symbologies are ASCII-only. ``_ascii`` would
        silently strip a non-ASCII character (and rewrite a double-quote, which
        also terminates the TSPL string literal), so the printed bars would no
        longer match the stored barcode and would fail to scan back. We surface
        a clear error up front instead of printing a label that cannot be
        scanned. This validates the print INPUT only — it does not change how
        barcodes are generated, stored, or formatted. An empty/blank barcode is
        allowed (title-only labels)."""
        bc = barcode or ""
        # The TSPL BARCODE command below encodes code[:48]; a longer barcode would
        # print bars (and human-readable digits) that DIFFER from the stored value,
        # so it would scan back to the wrong/no record. Reject up front rather than
        # silently truncate. (Auto-generated SKUs stay well under 48.)
        if len(bc) > 48:
            raise UserError(
                _(
                    "Barcode %(code)r is too long to print: %(n)d characters, but a "
                    "label can encode at most 48. Shorten the product's barcode, "
                    "then print again."
                )
                % {"code": barcode, "n": len(bc)}
            )
        for ch in bc:
            if ord(ch) < 0x20 or ord(ch) > 0x7E or ch == '"':
                raise UserError(
                    _(
                        "Barcode %(code)r cannot be printed: it contains a "
                        "character (%(char)r) the label printer does not support. "
                        "Barcodes must use plain ASCII letters, digits and basic "
                        "symbols. Correct the product's barcode, then print again."
                    )
                    % {"code": barcode, "char": ch}
                )

    def build_tspl(self, labels, copies=1):
        """Build a TSPL job (bytes) for ``labels`` — one physical label each.

        Layout: a 1-inch logo zone on the left, a divider, then on the right the
        brand line, the title (code + name), a sub-line of details, and a centred
        barcode with its digits below. Positions are in millimetres so a
        different stock re-flows; the profile's x/y offset nudges the whole label
        into the die-cut. Returns bytes because the logo BITMAP is binary."""
        self.ensure_one()
        copies = max(1, int(copies or 1))
        w, h = self.label_width_mm, self.label_height_mm
        d = self._dots
        xo, yo = d(self.x_offset_mm), d(self.y_offset_mm)
        right_edge = d(w) - d(2.0)
        logo_x, logo_y = xo + d(2.0), yo + d(1.5)
        logo_bw, logo_bh = d(22.0), d(max(6.0, h - 3.0))
        div_x = xo + d(25.4)  # end of the 1-inch logo zone
        rx = div_x + d(2.5)
        brand = _ascii(self.brand_line or "")
        no_logo = self.env.context.get("wms_print_no_logo")

        head = "\r\n".join(
            [
                "SIZE %s mm,%s mm" % (_fmt(w), _fmt(h)),
                "GAP %s mm,0 mm" % _fmt(self.gap_mm),
                "DIRECTION 1",
                "DENSITY %d" % int(self.density or 10),
                "SPEED %d" % int(self.speed or 3),
            ]
        ).encode("ascii")
        logo_cmd = b"" if no_logo else self._logo_bytes(logo_x, logo_y, logo_bw, logo_bh)

        blocks = []
        for lbl in labels:
            title = _ascii(lbl.get("title"))
            subtitle = _ascii(lbl.get("subtitle"))
            # Validate BEFORE _ascii so we reject (rather than silently drop) any
            # character the TSPL barcode symbology cannot reproduce. Otherwise the
            # printed bars would differ from the stored barcode and fail to scan
            # back. An empty barcode is allowed (some labels are title-only).
            self._assert_printable_barcode(lbl.get("barcode"))
            code = _ascii(lbl.get("barcode"))
            if not (title or code):
                continue
            parts = [b"CLS"]
            parts.append(
                logo_cmd
                or ("BOX %d,%d,%d,%d,2" % (logo_x, logo_y, logo_bw, logo_bh)).encode("ascii")
            )
            parts.append(
                ("BAR %d,%d,2,%d" % (div_x, yo + d(1.0), d(max(4.0, h - 2.0)))).encode("ascii")
            )
            if brand:
                parts.append(
                    ('TEXT %d,%d,"1",0,1,1,"%s"' % (rx, yo + d(0.8), brand[:52])).encode("ascii")
                )
            if title:
                parts.append(
                    ('TEXT %d,%d,"3",0,1,1,"%s"' % (rx, yo + d(3.0), title[:26])).encode("ascii")
                )
            if subtitle:
                parts.append(
                    ('TEXT %d,%d,"1",0,1,1,"%s"' % (rx, yo + d(7.5), subtitle[:48])).encode("ascii")
                )
            if code:
                sym, narrow, wide, bx = self._barcode_params(code, rx, right_edge)
                bar_top = yo + d(10.0)
                # Reserve room UNDER the bars for the human-readable digits
                # (HRI=1). A fixed 11 mm bar height ignored both the y-offset and
                # that readable line, so on the 100x25 mm stock the digits printed
                # off the bottom edge into the die-cut gap (confirmed on real
                # TE244 output — the SKU under each barcode was clipped). Size the
                # bars to the space that actually remains above a bottom margin.
                hri_reserve = d(5.0)  # human-readable line (~3 mm) + bottom margin
                avail = d(h) - hri_reserve - bar_top
                bar_h = max(d(8.0), min(avail, d(11.0)))
                parts.append(
                    (
                        'BARCODE %d,%d,"%s",%d,1,0,%d,%d,"%s"'
                        % (bx, bar_top, sym, bar_h, narrow, wide, code[:48])
                    ).encode("ascii")
                )
            parts.append(("PRINT 1,%d" % copies).encode("ascii"))
            blocks.append(b"\r\n".join(parts))
        if not blocks:
            raise UserError(_("Nothing to print: the selected records have no barcode."))
        return head + b"\r\n" + b"\r\n".join(blocks) + b"\r\n"

    # ---------------------------------------------------------------------
    # sending
    # ---------------------------------------------------------------------
    def send_raw(self, payload):
        """Send raw bytes to this printer. Spooler (Windows) or network (9100)."""
        self.ensure_one()
        if isinstance(payload, str):
            payload = payload.encode("ascii", "replace")
        if self.connection == "network":
            try:
                with socket.create_connection((self.host, self.port or 9100), timeout=6) as sock:
                    sock.sendall(payload)
            except OSError as exc:
                raise UserError(
                    _("Could not reach printer %(name)s at %(host)s:%(port)s — %(err)s")
                    % {
                        "name": self.name,
                        "host": self.host,
                        "port": self.port or 9100,
                        "err": exc,
                    }
                )
            return True
        # ---- Windows spooler (USB / local) ----
        try:
            import win32print
        except ImportError:
            raise UserError(
                _(
                    "Direct USB printing needs pywin32 on the server (Windows). "
                    "It is not available here. Use a Network printer, or print the "
                    "PDF label as a fallback."
                )
            )
        if not self.system_name:
            raise UserError(_("This printer has no Windows printer name set."))
        available = self.list_system_printers()
        if self.system_name not in available:
            raise UserError(
                _(
                    "Printer '%(name)s' was not found on the server.\nAvailable: "
                    "%(list)s\n\nFix the name in Configuration → Label Printers, or "
                    "check the printer is on."
                )
                % {"name": self.system_name, "list": ", ".join(available) or "(none)"}
            )
        # OpenPrinter is INSIDE the try so a printer that goes offline/locked
        # between the availability check above and here surfaces as the clean
        # UserError below rather than a raw pywin32 traceback. handle starts as
        # None so the finally only closes a handle we actually opened.
        handle = None
        try:
            handle = win32print.OpenPrinter(self.system_name)
            win32print.StartDocPrinter(handle, 1, ("WMS label", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
        except Exception as exc:  # noqa: BLE001 - surface a clean operator error
            _logger.exception("Direct print to %s failed", self.system_name)
            raise UserError(
                _(
                    "Printing to '%(name)s' failed: %(err)s\n\nCheck the printer "
                    "is on, connected, and not paused, then try again."
                )
                % {"name": self.system_name, "err": exc}
            )
        finally:
            if handle is not None:
                # A failure while closing must not mask the real print error
                # above, nor leak a traceback to the operator — best-effort.
                try:
                    win32print.ClosePrinter(handle)
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    _logger.exception("ClosePrinter cleanup failed for %s", self.system_name)
        return True

    def print_labels(self, labels, copies=1):
        """Build TSPL for ``labels`` and send it. Returns the label count.

        With ``wms_print_dry_run`` in the context the TSPL string is returned
        instead of being sent (tests / preview)."""
        self.ensure_one()
        tspl = self.build_tspl(labels, copies=copies)
        if self.env.context.get("wms_print_dry_run"):
            return tspl
        self.send_raw(tspl)
        return len([lbl for lbl in labels if lbl.get("barcode") or lbl.get("title")])

    # ---------------------------------------------------------------------
    # UI actions
    # ---------------------------------------------------------------------
    def action_test_print(self):
        """Print a sample label so the admin can confirm setup + alignment."""
        self.ensure_one()
        self.print_labels([{"title": "TEST", "subtitle": self.name, "barcode": "WMS-TEST-1"}])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Test label sent"),
                "message": _("A test label was sent to %s.") % self.name,
                "sticky": False,
            },
        }

    def action_detect_printers(self):
        """Show which Windows printers the server can see (helps fill the name)."""
        names = self.list_system_printers()
        msg = (
            _("Printers on this PC:\n%s") % "\n".join("• " + n for n in names)
            if names
            else _("No local printers detected (or not running on Windows).")
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "title": _("Detected printers"),
                "message": msg,
                "sticky": True,
            },
        }


def _fmt(value):
    """Trim a mm value for a TSPL command: 25.0 -> '25', 25.4 -> '25.4'."""
    text = "%.2f" % float(value or 0.0)
    return text.rstrip("0").rstrip(".") or "0"

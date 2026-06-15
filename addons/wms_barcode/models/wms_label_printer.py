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
    def build_tspl(self, labels, copies=1):
        """Build a TSPL job string for ``labels`` (list of dicts with optional
        ``title``, ``subtitle`` and ``barcode``). One physical label per dict.

        Layout for the 100x25 mm sticker: a title line + optional sub-line at the
        top, then a Code128 barcode filling the lower half with its digits under
        it. All positions derive from the configured media size, so a different
        stock just re-flows. The x/y offset shifts the whole label to align it
        inside the die-cut.
        """
        self.ensure_one()
        copies = max(1, int(copies or 1))
        w, h = self.label_width_mm, self.label_height_mm
        mx = self._dots(2.5) + self._dots(self.x_offset_mm)
        top = self._dots(self.y_offset_mm)
        # Vertical layout (dots): title band, then barcode band + human-readable.
        title_y = top + self._dots(1.5)
        sub_y = top + self._dots(6.0)
        has_sub = h >= 22  # only room for a sub-line on >= ~22 mm tall stock
        bar_y = top + self._dots(9.0 if has_sub else 6.0)
        bar_h = self._dots(min(11.0, h - 13.0)) if has_sub else self._dots(min(13.0, h - 8.0))
        bar_h = max(bar_h, self._dots(8.0))  # scannable floor
        narrow = max(_MIN_NARROW_DOTS, self._dots(0.33))
        wide = narrow * 2

        head = [
            "SIZE %s mm,%s mm" % (_fmt(w), _fmt(h)),
            "GAP %s mm,0 mm" % _fmt(self.gap_mm),
            "DIRECTION 1",
            "DENSITY %d" % int(self.density or 10),
            "SPEED %d" % int(self.speed or 3),
        ]
        body = []
        for lbl in labels:
            title = _ascii(lbl.get("title"))
            subtitle = _ascii(lbl.get("subtitle"))
            barcode = _ascii(lbl.get("barcode"))
            cmds = ["CLS"]
            if title:
                cmds.append('TEXT %d,%d,"4",0,1,1,"%s"' % (mx, title_y, title[:24]))
            if subtitle and has_sub:
                cmds.append('TEXT %d,%d,"2",0,1,1,"%s"' % (mx, sub_y, subtitle[:48]))
            if barcode:
                cmds.append(
                    'BARCODE %d,%d,"128",%d,1,0,%d,%d,"%s"'
                    % (mx, bar_y, bar_h, narrow, wide, barcode[:48])
                )
            elif not title:
                # Nothing to print for this record — skip a blank feed.
                continue
            cmds.append("PRINT 1,%d" % copies)
            body.append("\r\n".join(cmds))
        if not body:
            raise UserError(_("Nothing to print: the selected records have no barcode."))
        return "\r\n".join(head + body) + "\r\n"

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
        handle = win32print.OpenPrinter(self.system_name)
        try:
            win32print.StartDocPrinter(handle, 1, ("WMS label", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
        except Exception as exc:  # noqa: BLE001 - surface a clean operator error
            _logger.exception("Direct print to %s failed", self.system_name)
            raise UserError(
                _("Printing to '%(name)s' failed: %(err)s") % {"name": self.system_name, "err": exc}
            )
        finally:
            win32print.ClosePrinter(handle)
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

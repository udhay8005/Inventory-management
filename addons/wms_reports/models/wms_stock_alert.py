"""Low-stock alerts (Batch 6).

A daily cron tells WMS managers which products have fallen to or below their
reorder level, so the buyer acts before a stock-out. Delivery:

  * In-app (Discuss inbox) ALWAYS — reuses the established per-manager
    message_post pattern.
  * Email ONLY when the System Parameter ``wms_reports.alert_email`` is ``1``
    (best-effort: a missing mail server can never break the cron).

Restore-failure and expiry alerts already exist (wms.backup.audit,
wms.expiry.alert); this fills the remaining gap — proactive reorder warnings.
"""

import logging

from markupsafe import Markup, escape
from odoo import api, models

from .wms_notify import notify_wms_managers

_logger = logging.getLogger(__name__)


class WmsStockAlert(models.AbstractModel):
    _name = "wms.stock.alert"
    _description = "WMS low-stock alert dispatcher"

    @api.model
    def _cron_check_low_stock(self):
        """Notify managers of products at/below reorder level. Best-effort;
        silent when nothing needs reordering."""
        if "wms.forecast" not in self.env:
            return
        low = (
            self.env["wms.forecast"]
            .sudo()
            .search([("reorder_qty", ">", 0)], order="reorder_qty desc")
        )
        if not low:
            return
        # FPAT High: escape() the product name + UoM. A product named
        # '<script>alert(1)</script>' would otherwise post live HTML into
        # every manager's Discuss Inbox - stored XSS that fires the next
        # time any manager opens their inbox. Markup-wrapping the row HTML
        # itself is fine because the literal template fragments are static
        # and the only injection vectors are escape()'d.
        rows = "".join(
            "<li><b>%s</b> — suggest ordering %g %s</li>"
            % (
                escape(f.product_id.display_name or ""),
                f.reorder_qty,
                escape(f.product_id.uom_id.name or ""),
            )
            for f in low[:50]
        )
        extra = "" if len(low) <= 50 else "<p>...and %d more.</p>" % (len(low) - 50)
        body = Markup(  # nosec B704 — template literal; rows/extra use escape()
            "<p>&#128201; <b>%d product(s) at or below reorder level.</b></p>"
            "<ul>%s</ul>%s"
            "<p>Open <i>WMS &#8594; Forecast / Reorder</i> to raise a purchase.</p>"
        ) % (
            len(low),
            Markup(rows),
            Markup(extra),
        )  # nosec B704
        notify_wms_managers(self.env, body, "WMS — %d product(s) need reordering" % len(low))

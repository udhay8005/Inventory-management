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

from markupsafe import Markup
from odoo import api, models

_logger = logging.getLogger(__name__)
_TRUE = ("1", "true", "True", "yes", "on")


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
        rows = "".join(
            "<li><b>%s</b> — suggest ordering %g %s</li>"
            % (
                f.product_id.display_name,
                f.reorder_qty,
                (f.product_id.uom_id.name or ""),
            )
            for f in low[:50]
        )
        extra = "" if len(low) <= 50 else "<p>...and %d more.</p>" % (len(low) - 50)
        body = Markup(
            "<p>&#128201; <b>%d product(s) at or below reorder level.</b></p>"
            "<ul>%s</ul>%s"
            "<p>Open <i>WMS &#8594; Forecast / Reorder</i> to raise a purchase.</p>"
        ) % (len(low), Markup(rows), Markup(extra))
        self._dispatch_to_managers(body, "WMS — %d product(s) need reordering" % len(low))

    @api.model
    def _dispatch_to_managers(self, body, subject):
        """In-app notice to every WMS manager; optional email when enabled.

        Uses message_notify (not partner.message_post) so the alert actually
        lands in each manager's Discuss Inbox + systray — a plain message_post
        on a partner record only reaches followers, which a user is NOT of
        their own contact, so it would never surface.
        """
        managers = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not managers or not managers.all_user_ids:
            return
        partners = managers.all_user_ids.partner_id
        try:
            self.env["mail.thread"].message_notify(
                partner_ids=partners.ids, body=body, subject=subject
            )
        except Exception:  # noqa: BLE001 - a notice must never break the cron
            _logger.exception("wms.stock.alert: in-app notify failed")

        email_on = (
            self.env["ir.config_parameter"].sudo().get_param("wms_reports.alert_email", "0")
            in _TRUE
        )
        if not email_on:
            return
        for user in managers.all_user_ids.filtered("email"):
            try:
                self.env["mail.mail"].sudo().create(
                    {
                        "subject": subject,
                        "body_html": body,
                        "email_to": user.email,
                        "auto_delete": True,
                    }
                ).send()
            except Exception:  # noqa: BLE001 - email is best-effort
                _logger.exception("wms.stock.alert: email failed for %s", user.login)

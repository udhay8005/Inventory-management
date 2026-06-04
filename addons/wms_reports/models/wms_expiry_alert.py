"""Expiry alert report for medicine, feed, fluid, pooja.

The trust now records `wms_expiry_date` on every perishable product
(medicine, feed, ghee, oil). This report surfaces what's about to
expire so the Store Keeper can rotate stock and the Admin can plan
the next purchase order.

Two slices in one view:
  * already expired           - drop / dispose, urgent
  * expiring within 30 days   - move to front of shelf, plan reorder
  * expiring within 90 days   - on the radar
  * comfortable               - hidden by default

A scheduled action posts a digest message to the WMS Manager every
Monday so the trust doesn't depend on someone remembering to open
the report.
"""

from markupsafe import Markup, escape
from odoo import api, fields, models, tools


class WmsExpiryAlert(models.Model):
    _name = "wms.expiry.alert"
    _description = "Products approaching expiry"
    _auto = False
    _order = "days_to_expiry, product_id"

    product_id = fields.Many2one("product.product", readonly=True)
    wms_product_kind = fields.Selection(
        related="product_id.wms_product_kind",
        string="Kind",
        readonly=True,
    )
    expiry_date = fields.Date(string="Expiry date", readonly=True)
    days_to_expiry = fields.Integer(
        string="Days to expiry",
        readonly=True,
        help="Negative = already expired. 0 = today. 30 = a month "
        "of grace. Color codes in the list view reflect urgency.",
    )
    on_hand = fields.Float(
        string="On hand (units)",
        readonly=True,
    )
    batch_number = fields.Char(string="Batch", readonly=True)
    status = fields.Selection(
        [
            ("expired", "Expired"),
            ("urgent", "Expires within 30 days"),
            ("soon", "Expires within 90 days"),
            ("ok", "More than 90 days left"),
        ],
        readonly=True,
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # The view joins product.product → product.template (for the
        # expiry date + kind + batch) and aggregates current on-hand
        # quantity from stock.quant. Products without an expiry date
        # are skipped entirely so the list stays focused on the
        # perishable subset.
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_expiry_alert AS
            WITH on_hand AS (
                SELECT sq.product_id, SUM(sq.quantity) AS qty
                  FROM stock_quant sq
                  JOIN stock_location sl ON sl.id = sq.location_id
                 WHERE sl.usage = 'internal'
                 GROUP BY sq.product_id
            )
            SELECT
                pp.id              AS id,
                pp.id              AS product_id,
                pt.wms_expiry_date AS expiry_date,
                (pt.wms_expiry_date - CURRENT_DATE)::int AS days_to_expiry,
                COALESCE(oh.qty, 0) AS on_hand,
                pt.wms_batch_number AS batch_number,
                CASE
                    WHEN pt.wms_expiry_date < CURRENT_DATE             THEN 'expired'
                    WHEN pt.wms_expiry_date <= CURRENT_DATE + 30       THEN 'urgent'
                    WHEN pt.wms_expiry_date <= CURRENT_DATE + 90       THEN 'soon'
                    ELSE 'ok'
                END AS status
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN on_hand oh ON oh.product_id = pp.id
            WHERE pt.wms_expiry_date IS NOT NULL
        """
        )

    # ------------------------------------------------------------------
    # Weekly digest cron - posts a chatter message to every WMS Manager
    # ------------------------------------------------------------------
    @api.model
    def _cron_post_expiry_digest(self):
        """Fired by ir.cron weekly. Walks the alert view, picks the
        urgent + expired rows, and posts a summary on every WMS Manager
        user's Inbox so they see it next time they open Odoo.

        Designed to be quiet when nothing is expiring: returns
        immediately if zero rows match.
        """
        urgent = self.search([("status", "in", ("expired", "urgent"))], order="days_to_expiry")
        if not urgent:
            return

        # Find all WMS Manager users (group_wms_manager).
        manager_group = self.env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
        if not manager_group:
            return
        manager_partners = manager_group.all_user_ids.partner_id

        if not manager_partners:
            return

        rows = [
            "<table style='border-collapse:collapse;font-family:Arial'>",
            "<tr><th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ccc'>Product</th>"
            "<th style='text-align:right;padding:4px 8px;border-bottom:1px solid #ccc'>On hand</th>"
            "<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ccc'>Expiry</th>"
            "<th style='text-align:right;padding:4px 8px;border-bottom:1px solid #ccc'>Days</th></tr>",
        ]
        for row in urgent[:30]:  # cap so the email doesn't get massive
            color = "#cc0000" if row.status == "expired" else "#cc6600"
            rows.append(
                "<tr>"
                f"<td style='padding:4px 8px'><b>{escape(row.product_id.display_name)}</b></td>"
                f"<td style='padding:4px 8px;text-align:right'>{row.on_hand:g}</td>"
                f"<td style='padding:4px 8px'>{row.expiry_date}</td>"
                f"<td style='padding:4px 8px;text-align:right;color:{color}'>"
                f"<b>{row.days_to_expiry:+d}</b></td>"
                "</tr>"
            )
        rows.append("</table>")
        # Markup() so Odoo 19 renders the HTML instead of escaping the tags to
        # visible text (every other message_post in the codebase does this).
        # Product names are escape()d above so a stray '&' / '<' can't break it.
        body = Markup(
            f"<p><b>{len(urgent)} product(s) expiring soon or already expired.</b></p>"
            + "".join(rows)
            + "<p><i>Full list: WMS &rsaquo; Reports &rsaquo; Expiry alerts.</i></p>"
        )

        # Post to each manager partner's inbox via a sudoed mail.thread
        # call. We attach to res.users so Odoo's notification system
        # routes it correctly per user.
        Users = self.env["res.users"].sudo()
        for user in manager_group.all_user_ids:
            Users.browse(user.id).message_post(
                body=body,
                subject="WMS: weekly expiry digest",
                message_type="notification",
                partner_ids=[user.partner_id.id],
            )

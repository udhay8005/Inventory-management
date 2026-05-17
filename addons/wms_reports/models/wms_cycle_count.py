"""Slot count-age tracking + weekly reminder cron.

Adds two computed fields on stock.location (slot scope) that show:
  - the date a slot was last physically counted (via Odoo's
    `stock.quant.last_count_date`, or fall back to the slot's last
    `stock.move` arrival), and
  - the integer days since.

A weekly cron flags slots stale > 30 days into a `wms.cycle.count.due`
SQL-view dashboard. Optional: posts a Discuss message to WMS Managers.
"""

import logging

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)


class StockLocationCount(models.Model):
    _inherit = "stock.location"

    wms_last_counted = fields.Datetime(
        compute="_compute_wms_count_age",
        store=True,
        index=True,
        help="Most recent of: the slot's quants' last in_date OR last "
        "inventory adjustment line landing here. Used to flag stale "
        "slots needing a physical recount.",
    )
    wms_days_since_count = fields.Integer(
        compute="_compute_wms_count_age",
        store=True,
        help="Days since the slot was last touched by a movement or "
        "inventory adjustment. 0 means counted today.",
    )

    @api.depends("quant_ids.in_date", "quant_ids.last_count_date")
    def _compute_wms_count_age(self):
        # Slots AND floor zones track count-age. Other types stay null.
        stockables = self.filtered(lambda loc: loc.wms_location_type in ("slot", "floor"))
        (self - stockables).update({"wms_last_counted": False, "wms_days_since_count": 0})
        if not stockables:
            return
        now = fields.Datetime.now()
        for loc in stockables:
            # Use Odoo's last_count_date where available; fall back to the
            # latest quant in_date so freshly-stocked slots aren't flagged.
            latest = max(
                (q.last_count_date or q.in_date or q.create_date for q in loc.quant_ids),
                default=False,
            )
            loc.wms_last_counted = latest or False
            loc.wms_days_since_count = (now - latest).days if latest else 0


class WmsCycleCountDue(models.Model):
    """Read-only SQL view: slots that haven't been counted in > 30 days.

    Used by the menu action *Cycle Count Due*. We compute days inline so
    even slots without a stored value (compute hasn't run) get included.
    """

    _name = "wms.cycle.count.due"
    _description = "Slots due for cycle count"
    _auto = False
    _order = "days_since_count desc"

    location_id = fields.Many2one("stock.location", readonly=True, string="Slot")
    rack_id = fields.Many2one("stock.location", readonly=True)
    last_counted = fields.Datetime(readonly=True)
    days_since_count = fields.Integer(readonly=True)
    on_hand = fields.Float(readonly=True)
    distinct_products = fields.Integer(readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_cycle_count_due AS
              SELECT s.id AS id,
                     s.id AS location_id,
                     r.id AS rack_id,
                     s.wms_last_counted AS last_counted,
                     s.wms_days_since_count AS days_since_count,
                     COALESCE(SUM(q.quantity), 0) AS on_hand,
                     COUNT(DISTINCT q.product_id) AS distinct_products
                FROM stock_location s
                LEFT JOIN stock_location c
                  ON c.id = s.location_id AND c.wms_location_type = 'compartment'
                LEFT JOIN stock_location r
                  ON r.id = c.location_id AND r.wms_location_type = 'rack'
                LEFT JOIN stock_quant q
                  ON q.location_id = s.id AND q.quantity > 0
               WHERE s.wms_location_type IN ('slot', 'floor')
                 AND COALESCE(s.wms_days_since_count, 999) > 30
            GROUP BY s.id, r.id
        """
        )


class WmsCycleCountReminderCron(models.AbstractModel):
    """Weekly cron entry point. Computes the count-due dashboard's row
    count and posts a notice to every WMS Manager via Discuss.
    Idempotent: if no slots are due, no message is sent.
    """

    _name = "wms.cycle.count.cron"
    _description = "Cycle count weekly reminder"

    @api.model
    def run_weekly_reminder(self):
        # Re-trigger compute so days_since_count is fresh
        stockables = self.env["stock.location"].search(
            [("wms_location_type", "in", ("slot", "floor"))],
        )
        stockables._compute_wms_count_age()

        due = self.env["wms.cycle.count.due"].search([])
        if not due:
            _logger.info("wms_cycle_count: no slots stale > 30 days, " "nothing to remind.")
            return

        managers = self.env.ref(
            "wms_location.group_wms_manager",
            raise_if_not_found=False,
        )
        if not managers:
            return
        recipients = managers.users
        if not recipients:
            return

        body = (
            "<p><b>%d slot(s)</b> haven't been counted in over 30 days. "
            "Open <i>WMS → Reports → Cycle Count Due</i> to walk through "
            "and reconcile them.</p>"
        ) % len(due)
        for user in recipients:
            user.partner_id.message_post(
                body=body,
                subject="WMS — Cycle count reminder",
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
        _logger.info(
            "wms_cycle_count: notified %d managers about " "%d stale slots.",
            len(recipients),
            len(due),
        )

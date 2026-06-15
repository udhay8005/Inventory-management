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

from markupsafe import Markup
from odoo import api, fields, models, tools

from .wms_notify import notify_wms_managers

_logger = logging.getLogger(__name__)


class StockLocationCount(models.Model):
    _inherit = "stock.location"

    wms_last_counted = fields.Datetime(
        compute="_compute_wms_last_counted",
        store=True,
        index=True,
        # Explicit compute_sudo=True (Odoo's default for a stored computed
        # field): the compute reads quant_ids, which a non-privileged keeper
        # may not have full access to. The on-read sibling below is
        # compute_sudo=False, so the two MUST use distinct compute methods —
        # see the NOTE before _compute_wms_last_counted.
        compute_sudo=True,
        help="Most recent date this slot was physically counted or had stock movement. Used to flag slots that are overdue for a recount.",
    )
    wms_days_since_count = fields.Integer(
        compute="_compute_wms_days_since_count",
        # NOT stored: a stored value only refreshes when a quant changes, so an
        # untouched slot would keep yesterday's count forever. Computed on read
        # it always reflects today; the overdue SQL view computes its own delta
        # inline from the stored wms_last_counted date.
        compute_sudo=False,
        help="Days since this slot was last counted or had stock movement. "
        "0 means it was touched today.",
    )

    # NOTE: wms_last_counted (store=True, compute_sudo=True) and
    # wms_days_since_count (store=False, compute_sudo=False) deliberately differ
    # in BOTH `store` and `compute_sudo`. Computed fields that share one compute
    # method must agree on those flags, or Odoo warns at registry load
    # ("inconsistent 'compute_sudo'/'store' for computed fields ..."). They are
    # split into two methods below precisely so each method is internally
    # consistent. Do not re-merge them.
    @api.depends("quant_ids.in_date", "quant_ids.last_count_date")
    def _compute_wms_last_counted(self):
        # Slots AND floor zones track count-age. Other types stay null.
        stockables = self.filtered(lambda loc: loc.wms_location_type in ("slot", "floor"))
        (self - stockables).wms_last_counted = False
        for loc in stockables:
            # Use Odoo's last_count_date where available; fall back to the
            # latest quant in_date so freshly-stocked slots aren't flagged.
            loc.wms_last_counted = (
                max(
                    (q.last_count_date or q.in_date or q.create_date for q in loc.quant_ids),
                    default=False,
                )
                or False
            )

    @api.depends("wms_last_counted")
    def _compute_wms_days_since_count(self):
        # Derived from the stored last-counted date so it is always fresh on
        # read (non-stored): today minus the last count. Non-stockables and
        # never-counted slots read 0. Identical result to the old shared
        # compute, just decoupled from quant access (no sudo needed).
        now = fields.Datetime.now()
        for loc in self:
            last = loc.wms_last_counted
            loc.wms_days_since_count = (now - last).days if last else 0


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
                     (CURRENT_DATE - s.wms_last_counted::date) AS days_since_count,
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
                 AND COALESCE(CURRENT_DATE - s.wms_last_counted::date, 999) > 30
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
        # Refresh the stored wms_last_counted (and flush it) so the SQL view's
        # inline CURRENT_DATE - last_counted delta is current before we read it.
        stockables = self.env["stock.location"].search(
            [("wms_location_type", "in", ("slot", "floor"))],
        )
        stockables._compute_wms_last_counted()
        stockables.flush_recordset(["wms_last_counted"])

        due = self.env["wms.cycle.count.due"].search([])
        if not due:
            _logger.info("wms_cycle_count: no slots stale > 30 days, " "nothing to remind.")
            return

        # Markup() so Odoo 19 renders the HTML instead of escaping it.
        body = Markup(
            "<p><b>%d slot(s)</b> haven't been counted in over 30 days. "
            "Open <i>WMS &rsaquo; Reports &rsaquo; Cycle Count Due</i> to walk "
            "through and reconcile them.</p>"
        ) % len(due)
        notify_wms_managers(self.env, body, "WMS - Cycle count reminder")
        _logger.info("wms_cycle_count: notified managers about %d stale slots.", len(due))

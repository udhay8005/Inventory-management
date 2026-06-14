"""Returnable-items overdue tracking (F3).

Returnable stock (tools, spares, some textiles/safety gear) goes out via a
Scan Issue with an *expected return date* stamped on the picking
(``wms_expected_return_date``, set by the Scan Issue wizard when any planned
product is ``wms_is_returnable``). Until the item comes back via Scan Return —
which flips ``wms_returned`` to True — the picking is "outstanding".

This module owns the *reporting + alerting* half of the feature:

  * ``wms.returns.due.report`` — a read-only SQL view (``_auto = False``,
    mirroring wms.consumption.value.report / wms.cycle.count.due) listing every
    outstanding returnable issue with a ``days_overdue`` figure computed in the
    database, plus a due-soon / overdue ``state``.
  * ``wms.returns.cron`` — a tiny AbstractModel hosting the daily
    ``_cron_check_overdue_returns`` entry point (mirrors wms.cycle.count.cron).
    It finds pickings whose expected return date has passed and that are still
    outstanding, dedupes by picking, and pings every WMS Manager through the
    shared ``notify_wms_managers`` helper (a bare message_post to a manager
    partner is silently dropped — see wms_notify). Quiet when nothing is
    overdue.

The expected-return SLA per product (``expected_return_days``) and the picking
fields (``wms_expected_return_date`` / ``wms_returned``) are added by the
sibling wms_location / wms_barcode F3 commits; this module only reads them.
``stock.picking`` is a transitive dependency (wms_reports -> wms_repair_damage
-> wms_barcode), so the columns exist by the time this view's init() runs.
"""

import logging

from markupsafe import Markup, escape
from odoo import api, fields, models, tools

from .wms_notify import notify_wms_managers

_logger = logging.getLogger(__name__)


class WmsReturnsDueReport(models.Model):
    """Read-only SQL view: outstanding returnable issues, with days overdue.

    One row per (picking, product) still out on loan: a done Scan Issue whose
    picking carries an expected return date, has not been marked returned, and
    has not been reversed (Undo). ``days_overdue`` is ``today -
    wms_expected_return_date`` where *today* is the date in the **company
    timezone** (negative while still within the window); ``state`` buckets the
    row into due-soon vs overdue for the list decoration.
    """

    _name = "wms.returns.due.report"
    _description = "Returnable items outstanding / overdue"
    _auto = False
    _order = "days_overdue desc, wms_expected_return_date"

    picking_id = fields.Many2one("stock.picking", string="Issue", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    department_id = fields.Many2one("wms.department", string="Department", readonly=True)
    wms_storekeeper_id = fields.Many2one("wms.storekeeper", string="Store Keeper", readonly=True)
    qty = fields.Float(string="Qty out", readonly=True)
    wms_expected_return_date = fields.Date(string="Expected return", readonly=True)
    days_overdue = fields.Integer(
        string="Days overdue",
        readonly=True,
        help="Days past the expected return date. Negative while still within "
        "the window (i.e. due in N days).",
    )
    state = fields.Selection(
        [("due_soon", "Due soon"), ("overdue", "Overdue")],
        string="Status",
        readonly=True,
    )

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW wms_returns_due_report AS
            SELECT
                sml.id AS id,
                sml.picking_id AS picking_id,
                sml.product_id AS product_id,
                sp.wms_department_id AS department_id,
                sp.wms_storekeeper_id AS wms_storekeeper_id,
                sml.quantity AS qty,
                sp.wms_expected_return_date AS wms_expected_return_date,
                -- "today" in the COMPANY timezone, not raw CURRENT_DATE (which is
                -- the UTC session date). This keeps days_overdue aligned with the
                -- trust's local calendar day and with the cron's
                -- fields.Date.context_today logic; raw CURRENT_DATE was off by one
                -- in the hours around UTC midnight on a non-UTC (e.g. IST) deploy.
                ((now() AT TIME ZONE COALESCE(cpart.tz, 'UTC'))::date
                    - sp.wms_expected_return_date) AS days_overdue,
                CASE
                    WHEN (now() AT TIME ZONE COALESCE(cpart.tz, 'UTC'))::date
                            > sp.wms_expected_return_date
                        THEN 'overdue'
                    ELSE 'due_soon'
                END AS state
            FROM stock_move_line sml
            JOIN stock_picking sp ON sp.id = sml.picking_id
            LEFT JOIN res_company comp ON comp.id = sml.company_id
            LEFT JOIN res_partner cpart ON cpart.id = comp.partner_id
            WHERE sp.wms_is_scan_issue = TRUE
                  AND sp.wms_expected_return_date IS NOT NULL
                  AND sp.wms_returned = FALSE
                  -- a reversed (Undone) issue came straight back; never "due".
                  AND sp.wms_reversed_by_id IS NULL
                  AND sml.state = 'done'
"""
        )


class WmsReturnsCron(models.AbstractModel):
    """Daily cron entry point for the overdue-returns alert.

    Idempotent / quiet-when-healthy: if no returnable issue is past its
    expected return date, no notification is sent. Deduped by picking so a
    multi-line issue raises at most one line per picking.
    """

    _name = "wms.returns.cron"
    _description = "Returnable items overdue alert"

    # How many overdue pickings to name explicitly in the notice before
    # collapsing the tail into a "+N more" line (keeps the Discuss body sane).
    _MAX_LISTED = 20

    @api.model
    def _cron_check_overdue_returns(self):
        """Find outstanding returnable issues whose expected return date has
        passed and notify every WMS Manager once. Silent when nothing is
        overdue."""
        today = fields.Date.context_today(self)
        pickings = (
            self.env["stock.picking"]
            .sudo()
            .search(
                [
                    ("wms_is_scan_issue", "=", True),
                    ("wms_returned", "=", False),
                    ("wms_expected_return_date", "!=", False),
                    ("wms_expected_return_date", "<", today),
                    ("wms_reversed_by_id", "=", False),
                ],
                order="wms_expected_return_date",
            )
        )
        if not pickings:
            _logger.info("wms.returns.cron: no overdue returnable issues.")
            return

        rows = []
        for picking in pickings[: self._MAX_LISTED]:
            days = (today - picking.wms_expected_return_date).days
            products = ", ".join(picking.move_ids.product_id.mapped("display_name")[:5])
            dept = picking.wms_department_id.display_name or ""
            rows.append(
                Markup("<li>%s &#8212; %s &#183; %s &#183; <b>%s day(s) overdue</b></li>")
                % (
                    escape(picking.name or "?"),
                    escape(products or "(no product)"),
                    escape(dept),
                    days,
                )
            )
        more = len(pickings) - self._MAX_LISTED
        tail = Markup("<li><i>+%d more&#8230;</i></li>") % more if more > 0 else Markup("")

        body = Markup(
            "<p>&#9888; <b>%d returnable item(s) are overdue.</b></p>"
            "<ul>%s%s</ul>"
            "<p>Open <i>WMS &rsaquo; Reports &rsaquo; Returns due / overdue</i> "
            "to follow up, then clear each one with <i>Scan Return</i>.</p>"
        ) % (len(pickings), Markup("").join(rows), tail)
        notify_wms_managers(self.env, body, "WMS - Returnable items overdue")
        _logger.info(
            "wms.returns.cron: notified managers about %d overdue issue(s).",
            len(pickings),
        )

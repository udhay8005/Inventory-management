"""One-button admin self-diagnostics: aggregates read-only health + data-
integrity checks into a single screen. REUSES wms.backup.audit._health_snapshot()
for DB/backup/disk and runs cheap GROUP BY/COUNT SQL probes for duplicates,
negative stock, missing barcodes, orphan slots, and dead stock. Every check is a
read-only SELECT - nothing here writes stock or can corrupt data.
"""

from markupsafe import Markup, escape
from odoo import api, fields, models

# (label, status-if-nonzero, sql, detail-format)
_PROBES = [
    (
        "Duplicate SKUs",
        "fail",
        "SELECT count(*) FROM (SELECT default_code FROM product_product "
        "WHERE default_code IS NOT NULL GROUP BY default_code HAVING count(*)>1) d",
        "%s duplicate SKU value(s)",
    ),
    (
        "Duplicate barcodes",
        "fail",
        "SELECT count(*) FROM (SELECT barcode FROM product_product "
        "WHERE barcode IS NOT NULL GROUP BY barcode HAVING count(*)>1) d",
        "%s duplicate barcode(s)",
    ),
    (
        "Negative on-hand",
        "fail",
        # Only USABLE (internal) locations matter here. Virtual locations —
        # Vendors, Customers, Production, Inventory adjustment, our own
        # "internal use" sink — are negative by normal double-entry design
        # (every receipt drives Vendors negative), so counting them made this
        # check FAIL on every live deployment. Restrict to usage='internal' so
        # it flags a real oversell (issued more than a slot held), not the
        # accounting counterparties.
        "SELECT count(*) FROM stock_quant q "
        "JOIN stock_location l ON l.id = q.location_id "
        "WHERE q.quantity < 0 AND l.usage = 'internal'",
        "%s quant(s) below zero",
    ),
    (
        "Storable products without a barcode",
        "warn",
        "SELECT count(*) FROM product_product pp JOIN product_template pt "
        "ON pt.id=pp.product_tmpl_id WHERE pt.is_storable=true AND pp.active=true "
        "AND coalesce(pp.barcode,'')=''",
        "%s product(s) need a barcode / label",
    ),
    (
        "Orphan slots (no compartment parent)",
        "warn",
        "SELECT count(*) FROM stock_location s WHERE s.wms_location_type='slot' "
        "AND NOT EXISTS (SELECT 1 FROM stock_location c WHERE c.id=s.location_id "
        "AND c.wms_location_type='compartment')",
        "%s slot(s) not under a compartment",
    ),
    (
        "Dead stock (no recent movement)",
        "warn",
        "SELECT count(*) FROM wms_forecast WHERE velocity_class='dead'",
        "%s product(s) flagged dead",
    ),
    (
        "Storage outside the warehouse tree (audit blind spot)",
        "fail",
        # UAT R4: the trust's entire structure had been built under a
        # parentless top-level location instead of WH/Stock. Scan Issue found
        # the stock (the FEFO planner has a fallback for that shape), so
        # nothing looked wrong — but the weekly audit builds its count list
        # from "child_of warehouse.lot_stock_id" and therefore generated no
        # line for any of those slots, and the stock-value report under-
        # reported. A counting system must never silently omit stock, so this
        # is a FAIL, not a warning. parent_path makes the subtree test a plain
        # prefix match, so this stays a cheap index scan.
        "SELECT count(*) FROM stock_location s "
        "WHERE s.wms_location_type IN "
        "('zone','rack','shelf','compartment','slot','floor') "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM stock_warehouse w "
        "  JOIN stock_location ws ON ws.id = w.lot_stock_id "
        "  WHERE s.parent_path LIKE ws.parent_path || '%%' )",
        "%s storage location(s) the audit and stock-value report cannot see",
    ),
]

_COLOUR = {"pass": "#15803d", "warn": "#b45309", "fail": "#b91c1c"}
_ICON = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}
_ORDER = {"fail": 0, "warn": 1, "pass": 2}


class WmsSelfDiagnostics(models.TransientModel):
    _name = "wms.self.diagnostics"
    _description = "WMS one-button self-diagnostics"

    result_html = fields.Html(string="Results", readonly=True, sanitize=False)
    overall = fields.Selection(
        [("pass", "All good"), ("warn", "Warnings"), ("fail", "Action needed")],
        string="Overall",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._populate()  # auto-run on open
        return records

    def _scalar(self, sql):
        self.env.cr.execute(sql)
        row = self.env.cr.fetchone()
        return (row[0] if row else 0) or 0

    @api.model
    def _run_checks(self):
        """Return a list of {check, status (pass/warn/fail), detail}. Read-only;
        each probe is isolated so one failure can't abort the rest."""
        checks = []
        try:
            snap = self.env["wms.backup.audit"].sudo()._health_snapshot()
            hs = snap.get("status", "CRITICAL")
            # Guard the None case: a system with no backup yet has age=None, and
            # "last_backup=%sh" would render the bare "last_backup=Noneh". Show
            # "never" instead (matches the dashboard's last_backup_label).
            age = snap.get("last_backup_age_hours")
            last_backup_txt = ("%sh" % age) if age is not None else "never"
            checks.append(
                {
                    "check": "System health (DB + backup file + disk free)",
                    "status": (
                        "pass" if hs == "HEALTHY" else ("warn" if hs == "DEGRADED" else "fail")
                    ),
                    "detail": "status=%s; db_reachable=%s; last_backup=%s; %s"
                    % (
                        hs,
                        snap.get("db_reachable"),
                        last_backup_txt,
                        "; ".join(snap.get("warnings") or []) or "no warnings",
                    ),
                }
            )
        except Exception as e:  # noqa: BLE001 - a probe error must not break the page
            checks.append(
                {"check": "System health", "status": "fail", "detail": "probe error: %s" % e}
            )

        for label, failstatus, sql, fmt in _PROBES:
            try:
                n = self._scalar(sql)
                checks.append(
                    {"check": label, "status": "pass" if not n else failstatus, "detail": fmt % n}
                )
            except Exception as e:  # noqa: BLE001
                checks.append({"check": label, "status": "warn", "detail": "check skipped: %s" % e})
        return checks

    def _populate(self):
        checks = self._run_checks()
        overall = "pass"
        if any(c["status"] == "fail" for c in checks):
            overall = "fail"
        elif any(c["status"] == "warn" for c in checks):
            overall = "warn"
        # check labels are static literals; detail can include str(exception)
        # so escape() both before interpolating into the Markup context.
        rows = Markup("").join(
            Markup(
                "<tr>"
                "<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb'><b style='color:{colour}'>{icon}</b></td>"
                "<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb'>{check}</td>"
                "<td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;color:#374151'>{detail}</td>"
                "</tr>"
            ).format(
                colour=_COLOUR[c["status"]],
                icon=_ICON[c["status"]],
                check=escape(c["check"]),
                detail=escape(c["detail"]),
            )
            for c in sorted(checks, key=lambda x: _ORDER.get(x["status"], 3))
        )
        self.write(
            {
                "overall": overall,
                "result_html": Markup(
                    "<table style='border-collapse:collapse;width:100%;font-family:Arial'>"
                    "<tr style='background:#f3f4f6'>"
                    "<th style='text-align:left;padding:6px 10px'>Result</th>"
                    "<th style='text-align:left;padding:6px 10px'>Check</th>"
                    "<th style='text-align:left;padding:6px 10px'>Detail</th></tr>"
                )
                + rows
                + Markup("</table>"),
            }
        )

    def action_run(self):
        self.ensure_one()
        self._populate()
        return {
            "type": "ir.actions.act_window",
            "res_model": "wms.self.diagnostics",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
            "name": "WMS Self-Diagnostics",
        }

"""Wave 2 #1 — Warehouse Intelligence KPI dashboard.

A single server-rendered page (/wms/intelligence) of real-time KPI tiles built
from the Wave-2 analytics models. No JS / charting deps — like the Wave-1
/wms/dashboard, it loads fast and reads the report models. Manager-gated.

The 13 spec KPIs are sourced from: wms.stock.health (total / near / expired /
recalled / quarantined / healthy buckets), wms.forecast (velocity classes,
overstock/understock risk, reorder), wms.damage / wms.repair.order (damaged /
under-repair), and wms.lot.expiry.risk (critical / high risk counts).
"""

from odoo import http
from odoo.http import request


class WmsIntelligenceDashboard(http.Controller):
    @http.route("/wms/intelligence", type="http", auth="user", website=False)
    def intelligence(self, **kw):
        env = request.env
        # Manager-gated: the handler sudo()-reads all stock analytics.
        if not env.user.has_group("wms_location.group_wms_manager"):
            return request.not_found()
        return request.render("wms_analytics.intelligence_dashboard", {"k": self._kpis(env)})

    def _kpis(self, env):
        def sc(model, domain):
            return env[model].sudo().search_count(domain)

        health = env["wms.stock.health"].sudo().search([])
        total_qty = sum(health.mapped("total_qty"))
        healthy = sum(health.mapped("healthy_qty"))
        inv_value = sum(env["wms.forecast"].sudo().search([]).mapped("stock_value"))
        return {
            "total_products": sc("product.product", [("is_storable", "=", True)]),
            "total_on_hand": total_qty,
            "inventory_value": inv_value,
            "near_expiry": sum(health.mapped("near_qty")),
            "expired": sum(health.mapped("expired_qty")),
            "recalled": sum(health.mapped("recall_qty")),
            "quarantined": sum(health.mapped("quarantine_qty")),
            "damaged": sc("wms.damage", [("state", "=", "confirmed")]),
            "under_repair": sc("wms.repair.order", [("state", "=", "in_repair")]),
            "dead_stock": sc("wms.forecast", [("velocity_class", "=", "dead")]),
            "fast_moving": sc("wms.forecast", [("velocity_class", "=", "fast")]),
            "slow_moving": sc("wms.forecast", [("velocity_class", "=", "slow")]),
            "overstock": sc("wms.forecast", [("overstock_risk", "in", ("medium", "high"))]),
            "low_stock": sc("wms.forecast", [("reorder_qty", ">", 0)]),
            "health_score": round(100.0 * healthy / total_qty, 1) if total_qty else 100.0,
            "risk_critical": sc("wms.lot.expiry.risk", [("risk_band", "=", "critical")]),
            "risk_high": sc("wms.lot.expiry.risk", [("risk_band", "=", "high")]),
        }

"""Wave 2 #1 + #11 — Warehouse Intelligence HTTP pages.

  * /wms/intelligence          — KPI tiles dashboard (#1)
  * /wms/intelligence/heatmap  — status-aware warehouse heat map (#11)

Both are server-rendered (no JS deps), manager/user gated, and read the Wave-2
analytics + Wave-1 perishable models. The heat map lives here (not in the
Wave-1 wms_reports map) because the status overlay needs perishable lot-state /
effective-expiry fields, and wms_reports sits BELOW wms_perishable in the
dependency graph — only wms_analytics (which depends on wms_perishable) can read
them.
"""

from odoo import fields, http
from odoo.http import request

# Status overlay colour + label, in strict precedence order (worst first).
_STATUS = {
    "recall": ("#7f1d1d", "Recall"),
    "quarantine": ("#b45309", "Quarantine"),
    "expired": ("#b91c1c", "Expired"),
    "near": ("#d97706", "Near expiry"),
}


class WmsIntelligenceDashboard(http.Controller):
    # ---- #1 KPI dashboard ------------------------------------------------
    @http.route("/wms/intelligence", type="http", auth="user", website=False)
    def intelligence(self, **kw):
        env = request.env
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

    # ---- #11 status-aware heat map ---------------------------------------
    @http.route("/wms/intelligence/heatmap", type="http", auth="user", website=False)
    def heatmap(self, **kw):
        env = request.env
        if not env.user.has_group("wms_location.group_wms_user"):
            return request.not_found()
        return request.render("wms_analytics.heatmap_page", {"groups": self._heatmap(env)})

    def _loc_status(self, env, location_ids):
        """Highest-priority perishable status among lots with live stock in
        these locations: recall > quarantine > expired > near-expiry > None."""
        if not location_ids:
            return None
        quants = (
            env["stock.quant"]
            .sudo()
            .search([("location_id", "in", list(location_ids)), ("quantity", ">", 0)])
        )
        if not quants:
            return None
        states = set(quants.mapped("lot_id.wms_lot_state"))
        if "recalled" in states:
            return "recall"
        if "quarantine" in states:
            return "quarantine"
        today = fields.Date.today()
        effs = [q.wms_effective_expiry for q in quants if q.wms_effective_expiry]
        if any(e < today for e in effs):
            return "expired"
        if any((e - today).days <= 30 for e in effs):
            return "near"
        return None

    @staticmethod
    def _occ_color(pct, on_hand):
        if on_hand <= 0:
            return "#e5e7eb", "Empty"
        if pct <= 0:
            return "#3b82f6", "Stocked"
        if pct >= 100:
            return "#dc2626", "Full"
        if pct >= 75:
            return "#f59e0b", "Most full"
        return "#16a34a", "OK"

    def _tile(self, env, rec, location_ids, pct, on_hand):
        """One tile dict: status colour wins over occupancy colour."""
        status = self._loc_status(env, location_ids)
        if status:
            color, label = _STATUS[status]
        else:
            color, label = self._occ_color(pct, on_hand)
        return {
            "name": rec.name,
            "color": color,
            "label": label,
            "on_hand": "%.0f" % (on_hand or 0.0),
        }

    def _heatmap(self, env):
        Location = env["stock.location"].sudo()
        zones = Location.search([("wms_location_type", "=", "zone")], order="complete_name")

        def build(parent, label):
            racks = Location.search(
                [("location_id", "=", parent.id), ("wms_location_type", "=", "rack")],
                order="name",
            )
            floors = Location.search(
                [("location_id", "=", parent.id), ("wms_location_type", "=", "floor")],
                order="name",
            )
            tiles = []
            for r in racks:
                slots = Location.search(
                    [("id", "child_of", r.id), ("wms_location_type", "=", "slot")]
                )
                on_hand = sum(slots.mapped("wms_current_qty"))
                occupied = sum(1 for s in slots if s.wms_current_qty > 0)
                pct = (occupied / len(slots) * 100.0) if slots else 0.0
                tiles.append(self._tile(env, r, slots.ids, pct, on_hand))
            for f in floors:
                tiles.append(self._tile(env, f, [f.id], f.wms_occupancy_pct, f.wms_current_qty))
            return {"label": label, "tiles": tiles}

        groups = [build(z, z.name) for z in zones]
        for wh in env["stock.warehouse"].sudo().search([]):
            g = build(wh.lot_stock_id, "%s / Unzoned" % wh.display_name)
            if g["tiles"]:
                groups.append(g)
        return [g for g in groups if g["tiles"]]

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

        # wms.stock.health is one row per company (tiny) — mapped is fine.
        health = env["wms.stock.health"].sudo().search([])
        total_qty = sum(health.mapped("total_qty"))
        healthy = sum(health.mapped("healthy_qty"))
        # Inventory value: aggregate in SQL rather than loading every forecast row.
        value_groups = env["wms.forecast"].sudo()._read_group([], aggregates=["stock_value:sum"])
        inv_value = value_groups[0][0] or 0.0 if value_groups else 0.0
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

    @staticmethod
    def _status_from_quants(quants):
        """Highest-priority perishable status for an in-memory quant set:
        recall > quarantine > expired > near-expiry > None. Pure (no query) so
        the heat map can resolve every tile from ONE batched quant search."""
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

    def _tile(self, rec, pct, on_hand, status):
        """One tile dict: status colour wins over occupancy colour."""
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
        """Status-aware heat map. Builds the tile structure first, then resolves
        every tile's perishable status from a SINGLE batched stock.quant query
        (no per-tile search — avoids an N+1 over racks/floors)."""
        Location = env["stock.location"].sudo()
        Quant = env["stock.quant"].sudo()
        zones = Location.search([("wms_location_type", "=", "zone")], order="complete_name")

        specs = []  # [{label, tiles: [{rec, pct, on_hand, loc_ids}]}]
        all_loc_ids = set()

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
                tiles.append({"rec": r, "pct": pct, "on_hand": on_hand, "loc_ids": set(slots.ids)})
                all_loc_ids.update(slots.ids)
            for f in floors:
                tiles.append(
                    {
                        "rec": f,
                        "pct": f.wms_occupancy_pct,
                        "on_hand": f.wms_current_qty,
                        "loc_ids": {f.id},
                    }
                )
                all_loc_ids.add(f.id)
            return {"label": label, "tiles": tiles}

        for z in zones:
            specs.append(build(z, z.name))
        for wh in env["stock.warehouse"].sudo().search([]):
            g = build(wh.lot_stock_id, "%s / Unzoned" % wh.display_name)
            if g["tiles"]:
                specs.append(g)

        # ONE quant query for every contributing location, grouped by location.
        quants_by_loc = {}
        if all_loc_ids:
            for q in Quant.search([("location_id", "in", list(all_loc_ids)), ("quantity", ">", 0)]):
                quants_by_loc.setdefault(q.location_id.id, Quant)
                quants_by_loc[q.location_id.id] |= q

        groups = []
        for g in specs:
            tiles = []
            for t in g["tiles"]:
                tq = Quant
                for lid in t["loc_ids"]:
                    tq |= quants_by_loc.get(lid, Quant)
                tiles.append(
                    self._tile(t["rec"], t["pct"], t["on_hand"], self._status_from_quants(tq))
                )
            if tiles:
                groups.append({"label": g["label"], "tiles": tiles})
        return groups

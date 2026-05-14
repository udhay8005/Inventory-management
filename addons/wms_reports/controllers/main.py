"""HTTP controller for the rack visual grid.

Renders an authenticated HTML page at /wms/rack/<id>/grid showing each rack's
6 levels × N dividers × 3 slots, color-coded by occupancy. Plain QWeb +
Bootstrap so it works inside Odoo's web client and on mobile browsers
without any JS framework dependencies.
"""
from odoo import http
from odoo.http import request


def _slot_color(occupancy_pct, on_hand):
    """Return a Bootstrap background class based on slot fill ratio."""
    if on_hand <= 0:
        return "bg-light text-muted"
    if occupancy_pct <= 0:           # has stock but no capacity hint
        return "bg-info text-white"
    if occupancy_pct >= 100:
        return "bg-danger text-white"
    if occupancy_pct >= 75:
        return "bg-warning"
    return "bg-success text-white"


class WmsRackGridController(http.Controller):

    @http.route("/wms/rack/<int:rack_id>/grid", type="http", auth="user", website=False)
    def rack_grid(self, rack_id, **kw):
        rack = request.env["stock.location"].browse(rack_id).sudo().exists()
        if not rack or rack.wms_location_type != "rack":
            return request.not_found()

        # Build matrix[level_idx][divider_idx] = list of slot dicts
        # Levels go top→bottom (L-6 at top so it matches physical view).
        Location = request.env["stock.location"].sudo()
        levels = Location.search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "level")],
            order="wms_level_number desc",
        )
        matrix = []
        rack_on_hand = 0.0
        total_slots = 0
        for level in levels:
            dividers = Location.search(
                [("location_id", "=", level.id),
                 ("wms_location_type", "=", "divider")],
                order="wms_divider_number asc",
            )
            level_row = {"level": level, "dividers": []}
            for divider in dividers:
                slots = Location.search(
                    [("location_id", "=", divider.id),
                     ("wms_location_type", "=", "slot")],
                    order="wms_slot_number asc",
                )
                cells = []
                for slot in slots:
                    on_hand = slot.wms_current_qty
                    pct = slot.wms_occupancy_pct
                    cells.append({
                        "slot": slot,
                        "on_hand": on_hand,
                        "occupancy_pct": pct,
                        "products": slot.wms_product_ids,
                        "color": _slot_color(pct, on_hand),
                    })
                    rack_on_hand += on_hand
                    total_slots += 1
                level_row["dividers"].append({"divider": divider, "slots": cells})
            matrix.append(level_row)

        return request.render("wms_reports.rack_grid_page", {
            "rack": rack,
            "matrix": matrix,
            "rack_on_hand": rack_on_hand,
            "total_slots": total_slots,
        })

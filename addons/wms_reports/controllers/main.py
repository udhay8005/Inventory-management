"""HTTP controllers for the rack visual grid + warehouse map.

Two pages:
  /wms/rack/<id>/grid     - one rack's 6×N×3 slot heat-map
  /wms/warehouse/map      - whole-warehouse summary: zones, racks, floors

Plain QWeb + Bootstrap so they work inside Odoo's web client and on
mobile browsers with no JS framework deps.
"""

from odoo import http
from odoo.http import request


def _slot_color(occupancy_pct, on_hand):
    """Return a Bootstrap background class based on slot fill ratio."""
    if on_hand <= 0:
        return "bg-light text-muted"
    if occupancy_pct <= 0:  # has stock but no capacity hint
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
                [("location_id", "=", level.id), ("wms_location_type", "=", "divider")],
                order="wms_divider_number asc",
            )
            level_row = {"level": level, "dividers": []}
            for divider in dividers:
                slots = Location.search(
                    [("location_id", "=", divider.id), ("wms_location_type", "=", "slot")],
                    order="wms_slot_number asc",
                )
                cells = []
                for slot in slots:
                    on_hand = slot.wms_current_qty
                    pct = slot.wms_occupancy_pct
                    cells.append(
                        {
                            "slot": slot,
                            "on_hand": on_hand,
                            "occupancy_pct": pct,
                            "products": slot.wms_product_ids,
                            "color": _slot_color(pct, on_hand),
                        }
                    )
                    rack_on_hand += on_hand
                    total_slots += 1
                level_row["dividers"].append({"divider": divider, "slots": cells})
            matrix.append(level_row)

        return request.render(
            "wms_reports.rack_grid_page",
            {
                "rack": rack,
                "matrix": matrix,
                "rack_on_hand": rack_on_hand,
                "total_slots": total_slots,
            },
        )

    @http.route("/wms/warehouse/map", type="http", auth="user", website=False)
    def warehouse_map(self, **kw):
        """Whole-warehouse overview: every zone with its racks + floor zones,
        colour-coded by % full. Single page, mobile-friendly.
        """
        Location = request.env["stock.location"].sudo()
        # Find every zone. If a warehouse has racks/floors directly under
        # WH/Stock with no Zone wrapper, also surface them under a
        # synthetic "Unzoned" group.
        zones = Location.search([("wms_location_type", "=", "zone")], order="complete_name")

        def _build_group(parent_loc, label):
            """Collect rack + floor children for a single parent location."""
            racks = Location.search(
                [
                    ("location_id", "=", parent_loc.id),
                    ("wms_location_type", "=", "rack"),
                ],
                order="wms_rack_code",
            )
            floors = Location.search(
                [
                    ("location_id", "=", parent_loc.id),
                    ("wms_location_type", "=", "floor"),
                ],
                order="name",
            )
            rack_items = []
            for r in racks:
                # Aggregate the rack's slots
                slots = Location.search(
                    [
                        ("id", "child_of", r.id),
                        ("wms_location_type", "=", "slot"),
                    ]
                )
                on_hand = sum(slots.mapped("wms_current_qty"))
                occupied = sum(1 for s in slots if s.wms_current_qty > 0)
                pct = (occupied / len(slots) * 100.0) if slots else 0.0
                rack_items.append(
                    {
                        "rec": r,
                        "on_hand": on_hand,
                        "slots_total": len(slots),
                        "slots_occupied": occupied,
                        "pct": pct,
                        # Pre-format on the Python side so the QWeb template
                        # doesn't have to use '%%' (which Odoo's XML parser
                        # collapses to '%' and breaks Python formatting).
                        "pct_label": "%.0f%%" % pct,
                        "on_hand_label": "%.0f" % on_hand,
                        "color": _slot_color(pct, on_hand),
                    }
                )
            floor_items = []
            for f in floors:
                on_hand = f.wms_current_qty
                pct = f.wms_occupancy_pct
                floor_items.append(
                    {
                        "rec": f,
                        "on_hand": on_hand,
                        "on_hand_label": "%.0f" % on_hand,
                        "pct": pct,
                        "products": f.wms_product_ids,
                        "color": _slot_color(pct, on_hand),
                    }
                )
            total_on_hand = sum(r["on_hand"] for r in rack_items) + sum(
                f["on_hand"] for f in floor_items
            )
            return {
                "label": label,
                "parent": parent_loc,
                "racks": rack_items,
                "floors": floor_items,
                "total_on_hand": total_on_hand,
            }

        groups = [_build_group(z, z.name) for z in zones]

        # Unzoned: items still living directly under any WH/Stock (no zone wrapper)
        warehouses = request.env["stock.warehouse"].sudo().search([])
        for wh in warehouses:
            unzoned = _build_group(wh.lot_stock_id, f"{wh.display_name} / Unzoned")
            if unzoned["racks"] or unzoned["floors"]:
                groups.append(unzoned)

        wh_total = sum(g["total_on_hand"] for g in groups)
        wh_racks = sum(len(g["racks"]) for g in groups)
        wh_floors = sum(len(g["floors"]) for g in groups)
        for g in groups:
            g["total_on_hand_label"] = "%.0f" % g["total_on_hand"]
        return request.render(
            "wms_reports.warehouse_map_page",
            {
                "groups": groups,
                "wh_total_label": "%.0f" % wh_total,
                "wh_racks": wh_racks,
                "wh_floors": wh_floors,
            },
        )

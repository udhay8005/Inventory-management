"""HTTP controllers for the rack visual grid + warehouse map.

Two pages:
  /wms/rack/<id>/grid     - one rack's shelves × columns grid heat-map
  /wms/warehouse/map      - whole-warehouse summary: zones, racks, floors

Plain QWeb + Bootstrap so they work inside Odoo's web client and on
mobile browsers with no JS framework deps. The rack grid template uses
CSS Grid with `grid-row` / `grid-column` spans so multi-shelf
compartments render at their natural height.
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

        Location = request.env["stock.location"].sudo()
        compartments = Location.search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "compartment")],
            order="wms_shelf_top asc, wms_column_index asc",
        )

        # Build a list of grid cells. Each cell carries its CSS grid span
        # coords (1-based) plus the aggregated occupancy of all slots
        # inside the compartment.
        #
        # The QWeb template inverts the row index so shelf 1 appears at
        # the *top* of the grid (matches the physical view: top shelf
        # is shelf 1, bottom shelf is shelf N).
        cells = []
        rack_on_hand = 0.0
        total_slots = 0
        shelves = rack.wms_shelf_count or 1
        columns = rack.wms_column_count or 1
        for c in compartments:
            slots = Location.search(
                [("location_id", "=", c.id), ("wms_location_type", "=", "slot")],
                order="wms_slot_number asc",
            )
            on_hand = sum(slots.mapped("wms_current_qty"))
            total_slots += len(slots)
            rack_on_hand += on_hand
            # Aggregate occupancy = filled slots / total slots.
            occupied = sum(1 for s in slots if s.wms_current_qty > 0)
            pct = (occupied / len(slots) * 100.0) if slots else 0.0
            cells.append(
                {
                    "compartment": c,
                    "slots": slots,
                    "on_hand": on_hand,
                    "on_hand_label": "%.0f" % on_hand,
                    "occupancy_pct": pct,
                    "pct_label": "%.0f%%" % pct,
                    "products": c.wms_product_ids,
                    "color": _slot_color(pct, on_hand),
                    # CSS grid-row uses `start / end`. We render shelf 1
                    # at the top, so for span (top=1, bottom=3) the CSS
                    # span is grid-row: 1 / 4.
                    "row_start": c.wms_shelf_top or 1,
                    "row_end": (c.wms_shelf_bottom or c.wms_shelf_top or 1) + 1,
                    "col_start": c.wms_column_index or 1,
                    "col_end": (c.wms_column_index or 1) + 1,
                }
            )

        return request.render(
            "wms_reports.rack_grid_page",
            {
                "rack": rack,
                "cells": cells,
                "shelves": shelves,
                "columns": columns,
                "rack_on_hand": rack_on_hand,
                "total_slots": total_slots,
                "rack_on_hand_label": "%.0f" % rack_on_hand,
            },
        )

    @http.route("/wms/warehouse/map", type="http", auth="user", website=False)
    def warehouse_map(self, **kw):
        """Whole-warehouse overview: every zone with its racks + floor zones,
        colour-coded by % full. Single page, mobile-friendly.
        """
        Location = request.env["stock.location"].sudo()
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

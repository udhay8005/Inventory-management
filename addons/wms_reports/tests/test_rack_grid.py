"""High - the rack visual grid must render a polyomino compartment (now drawn
cell-by-cell from wms_cells_json) without erroring. Smoke test the controller
end-to-end so the per-cell rendering path is exercised, not just the data."""

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_polyomino")
class TestRackGridPolyomino(HttpCase):
    def test_grid_renders_polyomino(self):
        parent = self.env.ref("stock.stock_location_stock")
        wiz = self.env["wms.rack.generator"].create(
            {
                "warehouse_id": self.env.ref("stock.warehouse0").id,
                "parent_location_id": parent.id,
                "rack_code": "RGRIDP",
                "shelf_count": 2,
                "column_count": 2,
                "default_slot_count": 1,
            }
        )
        rack = wiz._create_rack_from_spec(
            {
                "parent_location_id": parent.id,
                "rack_code": "RGRIDP",
                "rack_name": "Grid Poly",
                "shelves": 2,
                "columns": 2,
                "compartments": [
                    {
                        "shelf_top": 1,
                        "shelf_bottom": 2,
                        "column_left": 1,
                        "column_right": 2,
                        "cells": [[1, 1], [2, 1], [2, 2]],
                        "slot_count": 1,
                        "label": "L-Comp",
                    }
                ],
            }
        )
        self.authenticate("admin", "admin")
        resp = self.url_open("/wms/rack/%d/grid" % rack.id)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("wms-rack-grid", resp.text)

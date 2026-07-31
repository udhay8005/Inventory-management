"""High - non-rectangular (L/T/U polyomino) compartments must persist their
exact cell list in wms_cells_json. The generator computed the cells then threw
them away (the field never existed), so the warehouse map could only draw the
misleading bounding box."""

import json

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_polyomino")
class TestPolyominoCells(TransactionCase):
    def test_polyomino_compartment_persists_cells(self):
        parent = self.env.ref("stock.stock_location_stock")
        wiz = self.env["wms.rack.generator"].create(
            {
                "warehouse_id": self.env.ref("stock.warehouse0").id,
                "parent_location_id": parent.id,
                "rack_code": "RPOLY",
                "shelf_count": 2,
                "column_count": 2,
                "default_slot_count": 1,
            }
        )
        spec = {
            "parent_location_id": parent.id,
            "rack_code": "RPOLY",
            "rack_name": "Poly Rack",
            "shelves": 2,
            "columns": 2,
            "compartments": [
                {  # L-shape: 3 of the 4 bounding-box cells
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
        rack = wiz._create_rack_from_spec(spec)
        comp = self.env["stock.location"].search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "compartment")]
        )
        self.assertEqual(len(comp), 1)
        self.assertTrue(comp.wms_cells_json, "polyomino compartment must persist its cells")
        self.assertEqual(json.loads(comp.wms_cells_json), [[1, 1], [2, 1], [2, 2]])

    def test_rectangular_compartment_leaves_cells_empty(self):
        parent = self.env.ref("stock.stock_location_stock")
        wiz = self.env["wms.rack.generator"].create(
            {
                "warehouse_id": self.env.ref("stock.warehouse0").id,
                "parent_location_id": parent.id,
                "rack_code": "RRECT",
                "shelf_count": 1,
                "column_count": 2,
                "default_slot_count": 1,
            }
        )
        spec = {
            "parent_location_id": parent.id,
            "rack_code": "RRECT",
            "rack_name": "Rect Rack",
            "shelves": 1,
            "columns": 2,
            "compartments": [
                {  # full 1x2 rectangle -> not a polyomino
                    "shelf_top": 1,
                    "shelf_bottom": 1,
                    "column_left": 1,
                    "column_right": 2,
                    "cells": [[1, 1], [1, 2]],
                    "slot_count": 1,
                }
            ],
        }
        rack = wiz._create_rack_from_spec(spec)
        comp = self.env["stock.location"].search(
            [("location_id", "=", rack.id), ("wms_location_type", "=", "compartment")]
        )
        self.assertEqual(len(comp), 1)
        self.assertFalse(comp.wms_cells_json, "rectangles describe themselves with the bbox")

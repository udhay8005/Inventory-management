"""Wave 2 — Lot / Product / Warehouse movement ledgers.

Seeds an inbound receipt, an internal relocation, and an outbound issue for a
single lot-tracked product, then asserts each ledger surfaces the expected rows
with the correct ``direction`` and quantities.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestLedgers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customers = cls.env.ref("stock.stock_location_customers")

        cls.bin_a = cls.env["stock.location"].create(
            {
                "name": "LEDG Bin A",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.bin_b = cls.env["stock.location"].create(
            {
                "name": "LEDG Bin B",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "LEDG Medicine",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "barcode": "LEDGMED01",
            }
        )
        cls.lot = cls.env["stock.lot"].create(
            {
                "name": "LEDG-LOT-1",
                "product_id": cls.product.id,
                "company_id": cls.env.company.id,
            }
        )

        # 1) Inbound receipt: supplier -> Bin A (qty 100) -> direction 'in'.
        cls._move(cls, cls.supplier, cls.bin_a, 100.0)
        # 2) Internal relocation: Bin A -> Bin B (qty 40) -> direction 'internal'.
        cls._move(cls, cls.bin_a, cls.bin_b, 40.0)
        # 3) Outbound issue: Bin B -> customers (qty 25) -> direction 'out'.
        cls._move(cls, cls.bin_b, cls.customers, 25.0)
        cls.env.flush_all()

    def _move(self, src, dest, qty):
        """Create and complete one stock move of ``qty`` of the lot product."""
        move = self.env["stock.move"].create(
            {
                "description_picking": "LEDG %s->%s" % (src.name, dest.name),
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_uom": self.product.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
            }
        )
        move._action_confirm()
        # Drop any auto-created (lineless) reservation line so the only line
        # _action_done sees is ours, carrying the lot — needed for moves whose
        # source is external (the inbound receipt) where assign can't reserve.
        move.move_line_ids.unlink()
        ml = self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.product.id,
                "lot_id": self.lot.id,
                "quantity": qty,
                "location_id": src.id,
                "location_dest_id": dest.id,
            }
        )
        ml.move_id.picked = True
        move._action_done()
        return move

    def test_product_ledger_has_all_three_directions(self):
        rows = self.env["wms.product.ledger"].search([("product_id", "=", self.product.id)])
        self.assertEqual(len(rows), 3, "one ledger row per done move line")
        dirs = sorted(rows.mapped("direction"))
        self.assertEqual(dirs, ["in", "internal", "out"])

    def test_directions_match_endpoint_usage(self):
        Ledger = self.env["wms.product.ledger"]
        in_row = Ledger.search([("product_id", "=", self.product.id), ("direction", "=", "in")])
        self.assertEqual(in_row.quantity, 100.0)
        self.assertEqual(in_row.location_dest_id, self.bin_a)

        internal_row = Ledger.search(
            [("product_id", "=", self.product.id), ("direction", "=", "internal")]
        )
        self.assertEqual(internal_row.quantity, 40.0)
        self.assertEqual(internal_row.location_id, self.bin_a)
        self.assertEqual(internal_row.location_dest_id, self.bin_b)

        out_row = Ledger.search([("product_id", "=", self.product.id), ("direction", "=", "out")])
        self.assertEqual(out_row.quantity, 25.0)
        self.assertEqual(out_row.location_id, self.bin_b)

    def test_lot_ledger_only_lot_tracked_rows(self):
        rows = self.env["wms.lot.ledger"].search([("lot_id", "=", self.lot.id)])
        self.assertEqual(len(rows), 3, "all three moves were lot-tracked")
        self.assertTrue(all(r.lot_id == self.lot for r in rows))
        self.assertEqual(sum(rows.mapped("quantity")), 165.0)

    def test_warehouse_ledger_destination_warehouse(self):
        Ledger = self.env["wms.warehouse.ledger"]
        # The internal relocation lands in Bin B, inside the warehouse.
        internal_row = Ledger.search(
            [("product_id", "=", self.product.id), ("direction", "=", "internal")]
        )
        self.assertEqual(internal_row.location_dest_id, self.bin_b)
        self.assertEqual(internal_row.dest_warehouse_id, self.wh)

    def test_ledger_excludes_non_done(self):
        # A confirmed-but-not-done move must NOT appear (state filter).
        draft = self.env["stock.move"].create(
            {
                "description_picking": "LEDG draft",
                "product_id": self.product.id,
                "product_uom_qty": 7.0,
                "product_uom": self.product.uom_id.id,
                "location_id": self.bin_a.id,
                "location_dest_id": self.bin_b.id,
            }
        )
        draft._action_confirm()
        self.env.flush_all()
        rows = self.env["wms.product.ledger"].search([("product_id", "=", self.product.id)])
        self.assertEqual(len(rows), 3, "non-done moves are excluded from the ledger")

"""Wave 2 #15 — Advanced Traceability (wms.lot.traceability) SQL view.

Seeds one lot-tracked medicine batch from a named supplier, puts it on the
shelf, runs a real Scan Issue (stamping the issue dimensions + the animal),
sends a unit through a repair-station location, and asserts the traceability
view rolls up the whole chain: supplier / batch / received_on, current on-hand
+ representative location, first issue date + animal, repair count, and the
destroyed flag once the lot is marked destroyed.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestLotTraceability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        # Manager rights: marking a lot destroyed is part of the recall/QC path,
        # and the field group used here is manager-gated in the perishable module.
        cls.env.user.group_ids = [(4, cls.env.ref("wms_location.group_wms_manager").id)]

        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "TRACE Keeper"})
        cls.dept = cls.env["wms.department"].create({"name": "TRACE Veterinary", "code": "TRCVET"})
        cls.animal = cls.env["wms.animal"].create({"name": "TRACE Nandini", "tag": "TRC-COW-1"})
        cls.supplier = cls.env["res.partner"].create({"name": "TRACE Supplier"})

        # A representative slot to issue from + a repair-station location.
        cls.slot = cls.env["stock.location"].create(
            {
                "name": "TRACE Slot",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.repair_loc = cls.env["stock.location"].create(
            {
                "name": "TRACE Repair-Out",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
                "wms_is_repair": True,
            }
        )

        # medicine is auto lot-tracked (V20-003); far-dated (400d) to clear the
        # V20-022 short-dated-at-issue guard.
        cls.med = cls.env["product.product"].create(
            {
                "name": "TRACE Vaccine",
                "type": "consu",
                "is_storable": True,
                "barcode": "TRACEMED01",
                "wms_product_kind": "medicine",
            }
        )
        cls.med.standard_price = 20.0
        cls.far = fields.Datetime.now() + timedelta(days=400)
        cls.lot = cls.env["stock.lot"].create(
            {
                "name": "TRC-MED-LOT",
                "product_id": cls.med.id,
                "company_id": cls.env.company.id,
                "wms_supplier_id": cls.supplier.id,
                "wms_supplier_batch": "SUP-BATCH-7",
                "wms_supplier_invoice": "INV-7",
                "expiration_date": cls.far,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.med, cls.slot, 50.0, lot_id=cls.lot)
        cls.env.flush_all()

    def _row(self, lot):
        # Flush pending writes, then drop the SQL-view cache so a re-read after
        # changing the underlying lot/quant reflects the new state.
        self.env.flush_all()
        self.env["wms.lot.traceability"].invalidate_model()
        return self.env["wms.lot.traceability"].search([("lot_id", "=", lot.id)])

    def _issue(self, qty, animal=None):
        wiz = self.env["wms.scan.issue"].create(
            {
                "warehouse_id": self.wh.id,
                "requested_qty": qty,
                "last_scan": "TRACEMED01",
                "taken_by": "Vet",
                "ordered_by": "Manager",
                "usage_note": "traceability test",
                "storekeeper_id": self.keeper.id,
                "department_id": self.dept.id,
                "animal_id": animal.id if animal else False,
            }
        )
        wiz.action_plan()
        wiz.action_validate()
        self.assertTrue(wiz.picking_id, "the issue should have created a picking")
        return wiz.picking_id

    # ------------------------------------------------------------------ #

    def test_origin_and_current(self):
        # Before any movement: supplier metadata + full on-hand are surfaced.
        row = self._row(self.lot)
        self.assertTrue(row, "every lot must appear on the traceability view")
        self.assertEqual(row.lot_id, self.lot)
        self.assertEqual(row.product_id, self.med)
        self.assertEqual(row.partner_id, self.supplier)
        self.assertEqual(row.supplier_batch, "SUP-BATCH-7")
        self.assertEqual(row.supplier_invoice, "INV-7")
        self.assertAlmostEqual(row.on_hand, 50.0, places=2)
        self.assertEqual(row.current_location_id, self.slot)
        self.assertTrue(row.received_on, "received_on should fall back to lot create_date")
        self.assertEqual(row.lot_state, "available")
        self.assertFalse(row.destroyed)
        self.assertFalse(row.returned)
        self.assertEqual(row.repair_count, 0)
        self.assertFalse(row.first_issue_date)

    def test_first_issue_records_animal(self):
        self._issue(5.0, animal=self.animal)
        row = self._row(self.lot)
        self.assertTrue(row.first_issue_date, "an issue should set the first-issue date")
        self.assertEqual(row.animal_id, self.animal)
        # 50 received, 5 issued out -> 45 still on hand in the slot.
        self.assertAlmostEqual(row.on_hand, 45.0, places=2)
        self.assertEqual(row.current_location_id, self.slot)

    def test_repair_count_and_destroyed(self):
        # Move one unit of this lot INTO the repair-station location via a done
        # internal move, so the view counts it as a repair pass.
        move = self.env["stock.move"].create(
            {
                "description_picking": "TRACE to repair",
                "product_id": self.med.id,
                "product_uom_qty": 1.0,
                "product_uom": self.med.uom_id.id,
                "location_id": self.slot.id,
                "location_dest_id": self.repair_loc.id,
            }
        )
        move._action_confirm()
        move.move_line_ids.unlink()
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.med.id,
                "lot_id": self.lot.id,
                "quantity": 1.0,
                "location_id": self.slot.id,
                "location_dest_id": self.repair_loc.id,
            }
        )
        move.picked = True
        move._action_done()

        row = self._row(self.lot)
        self.assertEqual(row.repair_count, 1, "one move into a repair location = one repair")

        # Now mark the lot destroyed and re-check the lifecycle endpoint.
        self.lot.wms_lot_state = "destroyed"
        row = self._row(self.lot)
        self.assertTrue(row.destroyed, "a destroyed lot must surface destroyed=True")
        self.assertEqual(row.lot_state, "destroyed")

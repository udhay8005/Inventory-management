"""Wave 2 #12 — Cold Chain Workflow (vaccines).

An in-range reading leaves the lot available; an out-of-range reading on a
cold-chain vaccine lot auto-creates a QC hold (wms.lot.quarantine) and the lot
becomes held. The out-of-range path is exercised as a non-manager keeper to
prove the auto-hold's admin-elevation works (the keeper can record readings but
the quarantine create is manager-gated).
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_analytics")
class TestColdChain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "COLD Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        # Vaccine kind → auto lot-tracked + use_expiration_date + cold-chain True.
        cls.vaccine = cls.env["product.product"].create(
            {
                "name": "COLD Vaccine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "vaccine",
                "barcode": "COLDVAC01",
            }
        )
        # A non-manager keeper who is allowed to record readings.
        cls.keeper = cls.env["res.users"].create(
            {
                "name": "Cold Keeper",
                "login": "cold_keeper",
                "group_ids": [(4, cls.env.ref("wms_location.group_wms_user").id)],
            }
        )

    def _lot(self, name):
        """A far-dated vaccine lot with on-hand stock on the floor."""
        lot = self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.vaccine.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.vaccine, self.floor, 5, lot_id=lot)
        return lot

    def test_vaccine_defaults_to_cold_chain(self):
        self.assertTrue(self.vaccine.wms_cold_chain, "vaccine is cold-chain by default")
        self.assertEqual(self.vaccine.wms_temp_min, 2.0)
        self.assertEqual(self.vaccine.wms_temp_max, 8.0)
        self.assertEqual(self.vaccine.tracking, "lot", "vaccine is auto lot-tracked")

    def test_in_range_reading_leaves_lot_available(self):
        lot = self._lot("CC-OK")
        reading = (
            self.env["wms.cold.chain.reading"]
            .with_user(self.keeper)
            .create({"lot_id": lot.id, "temperature": 5.0})
        )
        self.assertTrue(reading.in_range, "5 C is inside the 2-8 C band")
        self.assertFalse(reading.quarantine_id, "an in-range reading raises no QC hold")
        self.assertEqual(lot.wms_lot_state, "available", "the lot stays issuable")

    def test_out_of_range_reading_quarantines_lot(self):
        lot = self._lot("CC-EXCURSION")
        reading = (
            self.env["wms.cold.chain.reading"]
            .with_user(self.keeper)
            .create({"lot_id": lot.id, "temperature": 14.5})
        )
        self.assertFalse(reading.in_range, "14.5 C is above the 8 C max")
        # A keeper (non-manager) recorded it, yet the protective hold was raised.
        self.assertTrue(reading.quarantine_id, "an out-of-range reading raises a QC hold")
        self.assertEqual(reading.quarantine_id.state, "held")
        self.assertIn(lot, reading.quarantine_id.lot_ids)
        lot.invalidate_recordset(["wms_lot_state"])
        self.assertEqual(lot.wms_lot_state, "quarantine", "the cold-broken lot is held")

    def test_below_range_also_quarantines(self):
        lot = self._lot("CC-FROZEN")
        reading = self.env["wms.cold.chain.reading"].create({"lot_id": lot.id, "temperature": -1.0})
        self.assertFalse(reading.in_range, "-1 C is below the 2 C min")
        self.assertTrue(reading.quarantine_id, "a too-cold reading also raises a QC hold")
        self.assertEqual(lot.wms_lot_state, "quarantine")

    def test_second_excursion_on_held_lot_is_noop(self):
        lot = self._lot("CC-DOUBLE")
        first = self.env["wms.cold.chain.reading"].create({"lot_id": lot.id, "temperature": 20.0})
        self.assertTrue(first.quarantine_id)
        second = self.env["wms.cold.chain.reading"].create({"lot_id": lot.id, "temperature": 21.0})
        self.assertFalse(second.quarantine_id, "an already-held lot is not double-quarantined")

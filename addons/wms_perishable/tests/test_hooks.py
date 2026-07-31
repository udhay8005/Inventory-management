"""V20-019 — the stable lifecycle hook (_wms_lifecycle_hook) fires at each
perishable lifecycle event, so downstream modules can extend behaviour without
touching FEFO / recall / quarantine internals."""

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestLifecycleHooks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "HK Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "HK Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "HK Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "HKMED01",
            }
        )
        cls.env.user.write({"group_ids": [(4, cls.env.ref("wms_location.group_wms_manager").id)]})

    def _lot(self, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )

    def _spy(self):
        events = []
        lot_cls = type(self.env["stock.lot"])
        original = lot_cls._wms_lifecycle_hook

        def spy(records, event, payload=None):
            events.append(event)
            return original(records, event, payload)

        return events, patch.object(lot_cls, "_wms_lifecycle_hook", spy)

    def test_recall_fires_recalled_then_released(self):
        lot = self._lot("HK-RC")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        recall = self.env["wms.lot.recall"].create(
            {"mode": "manual", "reason": "x", "lot_ids": [(6, 0, lot.ids)]}
        )
        events, spy = self._spy()
        with spy:
            recall.action_recall()
            recall.action_release()
        self.assertIn("recalled", events)
        self.assertIn("released", events)

    def test_quarantine_fires_quarantined_then_destroyed(self):
        lot = self._lot("HK-QC")
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, 5, lot_id=lot)
        events, spy = self._spy()
        with spy:
            q = self.env["wms.lot.quarantine"].create({"reason": "x", "lot_ids": [(6, 0, lot.ids)]})
            q.action_destroy()
        self.assertIn("quarantined", events)
        self.assertIn("destroyed", events)

    def test_receipt_fires_received(self):
        events, spy = self._spy()
        with spy:
            wiz = self.env["wms.scan.receipt"].create(
                {"warehouse_id": self.wh.id, "storekeeper_id": self.keeper.id, "qc_passed": True}
            )
            self.env["wms.scan.receipt.line"].create(
                {
                    "wizard_id": wiz.id,
                    "product_id": self.med.id,
                    "quantity": 5,
                    "location_dest_id": self.floor.id,
                    "wms_batch": "HK-RCV",
                    "wms_expiry": "2027-12-31",
                }
            )
            wiz.action_validate()
        self.assertIn("received", events)

# -*- coding: utf-8 -*-
"""In-service asset register (owner question #10).

Issuing a fan used to decrement stock and end the trail. These tests pin the
after-life record: what it is, where it is fitted, since when, and when it
next needs a service — including the fire-extinguisher case (refill due
yearly) that the trust previously tracked by memory.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_asset")
class TestAssetRegister(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.shed = cls.env["stock.location"].create(
            {
                "name": "ASSET-TEST-SHED",
                "usage": "internal",
                "location_id": warehouse.lot_stock_id.id,
            }
        )
        cls.fan = cls.env["product.template"].create(
            {"name": "ASSET Ceiling Fan", "wms_product_kind": "electrical"}
        )
        cls.extinguisher = cls.env["product.template"].create(
            {"name": "ASSET Fire Extinguisher", "wms_product_kind": "safety"}
        )

    def _asset(self, tmpl, **extra):
        vals = {
            "product_id": tmpl.product_variant_id.id,
            "location_id": self.shed.id,
            "installed_on": fields.Date.context_today(self.env["wms.asset"]),
        }
        vals.update(extra)
        return self.env["wms.asset"].create(vals)

    def test_01_register_gets_reference_and_defaults(self):
        asset = self._asset(self.fan, serial_no="FAN-001", installed_by="Ramesh")
        self.assertTrue(asset.name.startswith("ASSET/"), "got %r" % asset.name)
        self.assertEqual(asset.state, "in_service")
        self.assertFalse(asset.next_service_date, "no interval -> nothing is ever 'due'")
        self.assertFalse(asset.service_due)

    def test_02_service_due_countdown(self):
        """A fire extinguisher on a 365-day refill: installed a year ago is
        due; installed today is not."""
        today = fields.Date.context_today(self.env["wms.asset"])
        overdue = self._asset(
            self.extinguisher,
            serial_no="EXT-OLD",
            service_interval_days=365,
            installed_on=today - timedelta(days=400),
        )
        fresh = self._asset(self.extinguisher, serial_no="EXT-NEW", service_interval_days=365)
        self.assertEqual(overdue.next_service_date, today - timedelta(days=35))
        self.assertTrue(overdue.service_due, "400 days on a 365-day refill is due")
        self.assertFalse(fresh.service_due, "installed today is not due")

    def test_03_recording_a_service_restarts_the_clock(self):
        today = fields.Date.context_today(self.env["wms.asset"])
        asset = self._asset(
            self.extinguisher,
            serial_no="EXT-SERVICED",
            service_interval_days=365,
            installed_on=today - timedelta(days=400),
        )
        self.assertTrue(asset.service_due)
        asset.action_service_done()
        self.assertEqual(asset.last_service_date, today)
        self.assertEqual(asset.next_service_date, today + timedelta(days=365))
        self.assertFalse(asset.service_due, "a serviced asset is no longer due")

    def test_04_search_filter_finds_due_assets(self):
        today = fields.Date.context_today(self.env["wms.asset"])
        due = self._asset(
            self.fan,
            serial_no="FAN-DUE",
            service_interval_days=90,
            installed_on=today - timedelta(days=200),
        )
        ok = self._asset(self.fan, serial_no="FAN-OK", service_interval_days=90)
        # Assert the computed values first, so a future failure says whether
        # the countdown or the SEARCH broke.
        self.assertTrue(due.service_due, "200 days on a 90-day interval is due")
        self.assertFalse(ok.service_due)
        found = self.env["wms.asset"].search([("service_due", "=", True)])
        self.assertIn(due, found, "the Service-due filter must return the due asset")
        self.assertNotIn(ok, found, "it must NOT return assets that are not due")
        self.assertTrue(all(a.service_due for a in found), "the filter must only return due assets")
        self.assertEqual(
            self.env["wms.asset"].wms_assets_due_for_service().ids,
            found.ids,
            "the alert helper and the filter must agree",
        )

    def test_05_lifecycle_transitions(self):
        asset = self._asset(self.fan, serial_no="FAN-LIFE")
        asset.action_mark_under_repair()
        self.assertEqual(asset.state, "under_repair")
        asset.action_back_in_service()
        self.assertEqual(asset.state, "in_service")
        asset.action_remove()
        self.assertEqual(asset.state, "removed")
        asset.action_back_in_service()
        self.assertEqual(asset.state, "in_service", "a removed asset can be refitted")
        asset.action_scrap()
        self.assertEqual(asset.state, "scrapped")
        with self.assertRaises(UserError, msg="a scrapped asset cannot come back"):
            asset.action_back_in_service()

    def test_06_serial_is_unique(self):
        self._asset(self.fan, serial_no="FAN-UNIQUE")
        with self.assertRaises(Exception):
            self._asset(self.fan, serial_no="FAN-UNIQUE")
            self.env.flush_all()

    def test_07_scrapped_asset_is_not_due(self):
        today = fields.Date.context_today(self.env["wms.asset"])
        asset = self._asset(
            self.extinguisher,
            serial_no="EXT-SCRAP",
            service_interval_days=30,
            installed_on=today - timedelta(days=90),
        )
        self.assertTrue(asset.service_due)
        asset.action_scrap()
        self.assertFalse(asset.service_due, "a scrapped asset must drop off the service alert")

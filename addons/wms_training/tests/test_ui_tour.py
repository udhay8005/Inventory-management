# -*- coding: utf-8 -*-
"""Real-browser UI walkthrough (UAT R3).

Drives headless Chrome through the actual Odoo web client — opening the WMS
app, clicking menu entries, reading what renders, and creating a product on
the real form. This is the automated equivalent of an operator walking the
screens one by one, and it catches the class of defect engine tests cannot:
a broken view, a menu that leads nowhere, a field that is not on the form.

Skips itself (rather than failing the suite) when no Chrome is available,
so CI containers without a browser stay green.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_ui_tour")
class TestWmsUiTour(HttpCase):
    def test_ui_navigation_walkthrough(self):
        """Open the WMS app and walk the operational, configuration,
        pharmacy, intelligence and forecast screens."""
        self.start_tour("/odoo", "wms_ui_navigation", login="admin")

    def test_ui_product_create_flow(self):
        """The product-creation flow from manual UAT: name it, pick a WMS
        Kind on the classification tab, save cleanly."""
        self.start_tour("/odoo", "wms_ui_product_create", login="admin")

    def test_ui_asset_register_flow(self):
        """Register a fitted asset through the real form and record a
        service — the in-service register, proven usable by a human.

        The item and the shed are created HERE rather than picked from
        whatever the database happens to hold. Earlier versions of this tour
        typed a letter and took the first product offered, which passed on a
        copy of the trust's live data and failed on CI's freshly installed
        database (no products at all); naming a real shed failed the other way
        round. Server-side fixtures make the tour deterministic on both, and
        keep the browser steps testing the FORM rather than the seed data.
        """
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        self.env["stock.location"].create(
            {
                "name": "TOUR Asset Shed",
                "usage": "internal",
                "location_id": warehouse.lot_stock_id.id,
                "wms_location_type": "zone",
            }
        )
        self.env["product.template"].create(
            {"name": "TOUR Asset Fan", "wms_product_kind": "electrical"}
        )
        self.env.flush_all()
        self.start_tour("/odoo", "wms_ui_asset_register", login="admin")

    def test_ui_sweep_expired_flow(self):
        """The Manager's one-click expired-stock sweep."""
        self.start_tour("/odoo", "wms_ui_sweep_expired", login="admin")

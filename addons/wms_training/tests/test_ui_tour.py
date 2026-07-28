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

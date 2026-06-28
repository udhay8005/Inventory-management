"""Shared test base for the v20 Wave 1 perishable engine.

Per Phase-0 build condition #4 (docs/v20-perishable-engine/09-phase0-verification.md):
a single ``WmsLotTestBase`` + 0-skip tags. Wave 1 fixtures (a lot-tracked
expiry-sensitive product, two batches with different expiry dates, slots) land
here so every perishable test shares one deterministic setup. Scaffold only —
the helpers below are the seam, not the implementation.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class WmsLotTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "Perishable Test Keeper"})

    # ---- seams Wave 1 fills in (kept as documented placeholders) ----------
    @classmethod
    def _make_lot_product(cls, name, kind="medicine"):
        """Wave 1: create a tracking='lot' + use_expiration_date product of the
        given perishable kind. Returns product.product."""
        raise NotImplementedError("Wave 1 ticket V20-00x")

    @classmethod
    def _receive_lot(cls, product, qty, expiry, slot=None, batch=None):
        """Wave 1: receive ``qty`` of ``product`` under a lot with ``expiry``."""
        raise NotImplementedError("Wave 1 ticket V20-00x")

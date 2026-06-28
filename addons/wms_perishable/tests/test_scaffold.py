"""Scaffold smoke test — proves the v20 module installs cleanly on top of the
frozen v19 stack and the shared test base resolves. Replaced/expanded by the
real Wave 1 tests (FEFO, lot lifecycle, recall, quarantine, guards) as the
backlog in docs/v20-perishable-engine/ is implemented.
"""

from .common import WmsLotTestBase


class TestPerishableScaffold(WmsLotTestBase):
    def test_module_installs_and_base_fixtures_resolve(self):
        # The module is installable (it loaded), product_expiry is present
        # (the lot model carries the expiration field), and the shared base
        # fixtures resolve. This is the green seam Wave 1 builds on.
        self.assertTrue(self.wh, "a warehouse must exist")
        self.assertTrue(self.stock, "a stock location must exist")
        self.assertIn(
            "expiration_date",
            self.env["stock.lot"]._fields,
            "product_expiry must be installed (stock.lot.expiration_date present)",
        )

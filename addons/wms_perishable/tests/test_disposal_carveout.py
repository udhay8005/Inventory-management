"""V20-011c — expired stock stays DISPOSABLE (damageable) even though it is
blocked from issue, and the carve-out does not leak to the normal issue path."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_perishable")
class TestDisposalCarveout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "DC Keeper"})
        cls.floor = cls.env["stock.location"].create(
            {
                "name": "DC Floor",
                "usage": "internal",
                "location_id": cls.stock.id,
                "wms_location_type": "floor",
            }
        )
        cls.med = cls.env["product.product"].create(
            {
                "name": "DC Medicine",
                "type": "consu",
                "is_storable": True,
                "wms_product_kind": "medicine",
                "barcode": "DCMED01",
            }
        )

    def _expired_lot(self, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2020-01-01 00:00:00",
            }
        )

    def _seed(self, lot, qty):
        self.env["stock.quant"]._update_available_quantity(self.med, self.floor, qty, lot_id=lot)

    def _damage(self, qty):
        dmg = self.env["wms.damage"].create(
            {
                "product_id": self.med.id,
                "source_slot_id": self.floor.id,
                "quantity": qty,
                "wms_reported_by": "DC Reporter",
                "wms_authorized_by": "DC Manager",
                "wms_storekeeper_id": self.keeper.id,
            }
        )
        dmg.action_confirm()
        return dmg

    def test_expired_stock_can_be_damaged(self):
        # Before the carve-out this aborted ("nothing reserved"); now the damage
        # reserves the expired lot so the stock can be cleared off the shelf.
        self._seed(self._expired_lot("DC-EXP"), 5)
        dmg = self._damage(3.0)
        self.assertEqual(
            dmg.state, "confirmed", "damage must reserve+confirm against expired stock"
        )
        self.assertAlmostEqual(dmg.damage_value, 0.0, places=2)  # std price 0 here

    def test_carveout_does_not_leak_to_issue(self):
        # The same expired stock must STILL be excluded from a normal issue —
        # the carve-out is scoped to the damage flow only.
        self._seed(self._expired_lot("DC-EXP2"), 5)
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.med.id, 3, parent_location_id=self.stock.id
        )
        self.assertEqual(plan, [], "normal issue must still exclude expired stock")
        self.assertEqual(missing, 3)

    def test_non_expired_damage_unchanged(self):
        valid = self.env["stock.lot"].create(
            {
                "name": "DC-OK",
                "product_id": self.med.id,
                "company_id": self.env.company.id,
                "expiration_date": "2027-12-31 00:00:00",
            }
        )
        self._seed(valid, 5)
        dmg = self._damage(2.0)
        self.assertEqual(dmg.state, "confirmed")

    def test_carveout_flag_does_not_escape_to_a_later_issue(self):
        # Definitive refutation of the "context escape" concern: confirm a
        # damage of expired stock (which sets wms_allow_expired_removal inside
        # the damage flow), then plan a NORMAL issue in the SAME transaction —
        # the flag must NOT have leaked, so the issue still excludes the expired
        # stock left on the shelf. (with_context creates a new Environment; it
        # does not mutate a transaction-global context.)
        self._seed(self._expired_lot("DC-SEQ"), 10)
        self._damage(3.0)  # sets the carve-out flag within action_confirm
        plan, missing = self.env["stock.location"].find_oldest_quants_for_product(
            self.med.id, 3, parent_location_id=self.stock.id
        )
        self.assertEqual(plan, [], "the damage carve-out flag must not leak into a later issue")
        self.assertEqual(missing, 3)

"""F1 — Issue dimensions (Department / Purpose / Animal).

Proves:
  * the Scan Issue wizard defaults its Department to the seeded 'Other'
    department (mirrors the legacy issued_for='other' default),
  * a plain issue stamps wms_department_id on the picking and derives the
    legacy wms_issued_for from the department's legacy_issued_for map,
  * choosing a department + optional purpose + optional animal copies all
    three onto the resulting picking,
  * the back-fill migration maps a historical wms_issued_for='cows' picking
    (no department) to the Gaushala department, and is idempotent.
"""

import importlib.util
import os

from odoo.tests import TransactionCase, tagged


def _load_backfill_migration():
    """Load the version-dir post-migration script by path.

    The migrations folder is not an importable package (no __init__, the
    version dir name contains dots), so the test loads the module from its
    file path to call migrate() directly.
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "migrations",
        "19.0.1.26.0",
        "post-migration.py",
    )
    spec = importlib.util.spec_from_file_location("wms_barcode_f1_backfill", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged("post_install", "-at_install", "wms", "wms_dims")
class TestIssueDimensions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.keeper = cls.env["wms.storekeeper"].search([], limit=1) or cls.env[
            "wms.storekeeper"
        ].create({"name": "UAT Keeper DIM"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "DIM-TEST Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "DIMTEST001",
                "wms_product_kind": "consumable",
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 50.0)
        cls.dept_other = cls.env.ref("wms_location.dept_other")
        cls.dept_gaushala = cls.env.ref("wms_location.dept_gaushala")

    def _make_wizard(self, **extra):
        vals = {
            "warehouse_id": self.wh.id,
            "requested_qty": 2.0,
            "last_scan": "DIMTEST001",
            "taken_by": "Test Taker",
            "ordered_by": "Test Orderer",
            "usage_note": "dimensions test",
            "storekeeper_id": self.keeper.id,
        }
        vals.update(extra)
        return self.env["wms.scan.issue"].create(vals)

    def test_default_department_is_other(self):
        wiz = self._make_wizard()
        self.assertEqual(
            wiz.department_id,
            self.dept_other,
            "the wizard must default its Department to the seeded 'Other' department",
        )

    def test_issue_stamps_department_and_derives_issued_for(self):
        wiz = self._make_wizard()
        wiz.action_plan()
        wiz.action_validate()
        picking = wiz.picking_id
        self.assertEqual(picking.wms_department_id, self.dept_other)
        # 'Other' department's legacy_issued_for is 'other', so the legacy
        # column must be derived to 'other'.
        self.assertEqual(
            picking.wms_issued_for,
            self.dept_other.legacy_issued_for or "other",
            "wms_issued_for must be derived from the department's legacy map",
        )

    def test_issue_with_purpose_and_animal(self):
        purpose = self.env["wms.purpose"].search([], limit=1) or self.env["wms.purpose"].create(
            {"name": "DIM Purpose"}
        )
        animal = self.env["wms.animal"].create({"name": "DIM Cow", "tag": "DIM-TAG-001"})
        wiz = self._make_wizard(
            department_id=self.dept_gaushala.id,
            purpose_id=purpose.id,
            animal_id=animal.id,
        )
        wiz.action_plan()
        wiz.action_validate()
        picking = wiz.picking_id
        self.assertEqual(picking.wms_department_id, self.dept_gaushala)
        self.assertEqual(picking.wms_purpose_id, purpose)
        self.assertEqual(picking.wms_animal_id, animal)
        # Gaushala's legacy_issued_for is 'cows'.
        self.assertEqual(picking.wms_issued_for, "cows")

    def test_backfill_maps_legacy_cows_to_gaushala(self):
        # Seed a historical picking that only carries the legacy selection
        # (no department), as pre-F1 Scan Issue pickings did.
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh.int_type_id.id,
                "location_id": self.stock.id,
                "location_dest_id": self.stock.id,
                "origin": "Legacy issue",
                "wms_is_scan_issue": True,
                "wms_storekeeper_id": self.keeper.id,
                "wms_issued_for": "cows",
            }
        )
        self.assertFalse(picking.wms_department_id)

        migration = _load_backfill_migration()
        migration.migrate(self.env.cr, "19.0.1.26.0")
        picking.invalidate_recordset(["wms_department_id"])
        self.assertEqual(
            picking.wms_department_id,
            self.dept_gaushala,
            "back-fill must map legacy wms_issued_for='cows' to the Gaushala department",
        )
        # Legacy column is left untouched.
        self.assertEqual(picking.wms_issued_for, "cows")

        # Idempotent: a second run changes nothing.
        migration.migrate(self.env.cr, "19.0.1.26.0")
        picking.invalidate_recordset(["wms_department_id"])
        self.assertEqual(picking.wms_department_id, self.dept_gaushala)

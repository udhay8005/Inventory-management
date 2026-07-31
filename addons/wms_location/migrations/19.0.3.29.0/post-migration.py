"""UAT R4: re-home storage locations that sit outside the warehouse stock tree.

The live gaushala database had all 234 storage locations (both plots' zones,
racks, compartments, slots and bulk floors) hanging off a parentless top-level
location instead of under WH/Stock. Scan Issue still found the stock, but the
weekly audit and the stock-value report both scope to the warehouse tree, so
they skipped every one of those slots without a word.

This moves the parent link only — no stock moves, no renaming, no lost history.
"""

from odoo import SUPERUSER_ID, api
from odoo.addons.wms_location.hooks import _rehome_wms_structure


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # The move itself is the repair, so it must not be blocked by the very
    # constraint it satisfies while the tree is half-moved.
    _rehome_wms_structure(env(context=dict(env.context, wms_skip_tree_check=True)))

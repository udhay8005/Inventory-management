"""UAT R4 — two repairs for existing databases, including the live one.

1. Storage locations built OUTSIDE the warehouse stock tree. The live gaushala
   database had all 234 of them (both plots' zones, racks, compartments, slots
   and bulk floors) hanging off a parentless top-level location instead of
   under WH/Stock. Scan Issue still found the stock, but the weekly audit and
   the stock-value report both scope to the warehouse tree, so they skipped
   every one of those slots without a word. This moves the parent link only —
   no stock moves, no renaming, no lost history.

2. The consumed-goods sink was indistinguishable from a shelf. "Trust internal
   use" is where issued goods land, yet it is usage='internal' like any rack,
   so with an empty shelf the issue planner would plan an issue STRAIGHT OUT OF
   THE SINK — re-issuing goods that were already handed out. The sink is
   defined in a noupdate data block, so only a hook can stamp the new flag on
   an existing database.

Order matters: mark the sink FIRST. If the re-home were to fail on some
unusual tree, the far more dangerous phantom-issue hole is already closed.
"""

from odoo import SUPERUSER_ID, api
from odoo.addons.wms_location.hooks import _mark_trust_use_sink, _rehome_wms_structure


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _mark_trust_use_sink(env)
    # The move itself is the repair, so it must not be blocked by the very
    # constraint it satisfies while the tree is half-moved.
    _rehome_wms_structure(env(context=dict(env.context, wms_skip_tree_check=True)))

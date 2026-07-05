"""19.0.3.27.0 — enforce ₹-only currency + visible Unit of Measure on
existing databases (the live gaushala DB upgrades through this path).

Fresh installs get the same via wms_location's post_init_hook; this covers
databases that were installed before 19.0.3.27.0.
"""

from odoo import SUPERUSER_ID, api
from odoo.addons.wms_location.hooks import _apply_trust_defaults


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_trust_defaults(env)

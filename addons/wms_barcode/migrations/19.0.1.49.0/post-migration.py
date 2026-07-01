"""Bump the high-value approval threshold from the old Rs 5,000 default to the
spec's Rs 20,000 — but ONLY when it is still the untouched old default.

The threshold lives in ir.config_parameter ``wms_barcode.high_value_threshold``,
seeded inside a noupdate="1" block so a module upgrade never overwrites an
Admin's tuned value. That protection means an existing install that seeded the
old '5000' would keep '5000' forever after we changed the shipped default. This
migration closes that gap for the one specific case that matters:

  * value is exactly '5000'  -> set it to '20000' (the old default was never
    touched by the Admin, so realign it to the corrected spec value);
  * any other value (a real tuned number, blank, or already '20000') -> leave
    it alone.

Idempotent: a re-run finds '20000' (or a tuned value) and does nothing. A fresh
install never runs migrations and gets '20000' straight from the data seed.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_OLD_DEFAULT = "5000"
_NEW_DEFAULT = "20000"
_PARAM = "wms_barcode.high_value_threshold"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    current = env["ir.config_parameter"].sudo().get_param(_PARAM)
    if (current or "").strip() == _OLD_DEFAULT:
        env["ir.config_parameter"].sudo().set_param(_PARAM, _NEW_DEFAULT)
        _logger.info(
            "wms_barcode: high-value approval threshold realigned Rs %s -> Rs %s "
            "(untouched old default).",
            _OLD_DEFAULT,
            _NEW_DEFAULT,
        )
    else:
        _logger.info(
            "wms_barcode: high-value threshold is '%s' (tuned or already current); left unchanged.",
            current,
        )

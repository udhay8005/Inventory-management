from . import controllers, models, wizards

# `tests` is discovered automatically by Odoo when --test-enable is passed.
#
# Note: a `_create_default_storekeeper(env)` helper used to live here
# but was never wired in __manifest__.py via `post_init_hook`, so it
# was dead code (the audit confirmed 0 references project-wide).
# Removed in the Day-1 quick-win cleanup. If a default Store Keeper
# user is needed at install time, declare one in
# addons/wms_location/demo/demo.xml instead — that path is honoured
# by Odoo's loader and visible in source review.

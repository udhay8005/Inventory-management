"""Install / upgrade hooks for wms_location.

Two trust-wide defaults are enforced here rather than via data records,
because plain XML records can't do either job reliably:

* the company currency (a fresh Odoo defaults to USD, and an XML write of
  ``res.company.currency_id`` gets reset by a later install step), and
* the visible Unit-of-Measure field (an *implied* group that must propagate
  to already-existing internal users — a data record only sets the implication,
  it does not re-materialise access for current users).

Both settle findings from real operator UAT: every Cost field was rendering
"$" instead of ₹, and the Unit-of-Measure field was hidden on the product form.
The logic is idempotent, so it is safe to re-run on every upgrade.
"""


def _apply_trust_defaults(env):
    """Force ₹-only currency and a visible Unit-of-Measure field. Idempotent.

    Called from ``post_init_hook`` (fresh install) and the 19.0.3.27.0
    post-migration (existing databases, including the live gaushala one).
    """
    # 1. Indian Rupee only — the brief mandates "₹ only, no foreign currency".
    inr = env.ref("base.INR", raise_if_not_found=False)
    if inr:
        if not inr.active:
            inr.active = True
        stale = env["res.company"].search([]).filtered(lambda c: c.currency_id != inr)
        if stale:
            stale.currency_id = inr

    # 2. Surface the Unit-of-Measure field. res.config.settings is the
    #    canonical toggle: it implies uom.group_uom on the internal-user
    #    group AND propagates the access to existing users, which a raw
    #    implied_ids write does not guarantee.
    if env.ref("uom.group_uom", raise_if_not_found=False):
        env["res.config.settings"].create({"group_uom": True}).execute()


def post_init_hook(env):
    """Run once when wms_location is first installed."""
    _apply_trust_defaults(env)

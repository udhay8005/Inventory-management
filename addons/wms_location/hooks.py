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

``_rehome_wms_structure`` repairs a third, structural finding — storage
locations built outside the warehouse stock tree, which made the weekly audit
skip them silently.
"""

import logging

_logger = logging.getLogger(__name__)

# The location types that make up physical storage. Deliberately excludes the
# WMS service locations (trust-internal-use sink, Damage, Repair-Out): those
# carry no wms_location_type and legitimately live outside the storage tree.
_WMS_STRUCTURAL_TYPES = ("zone", "rack", "shelf", "compartment", "slot", "floor")


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


def _mark_trust_use_sink(env):
    """Flag "Trust internal use" as the consumed-goods sink. Idempotent.

    Why this needs a hook: the sink is defined in a ``noupdate="1"`` data
    block, so adding the field to the XML only reaches FRESH installs. Every
    existing database — including the live gaushala one — has to be stamped
    here, and until it is, the issue planner cannot tell the sink from a shelf.
    """
    sink = env.ref("wms_location.stock_location_trust_use", raise_if_not_found=False)
    if sink and not sink.wms_is_trust_use:
        sink.wms_is_trust_use = True
        _logger.info("wms_location: marked %s as the consumed-goods sink.", sink.complete_name)


def post_init_hook(env):
    """Run once when wms_location is first installed."""
    _apply_trust_defaults(env)
    _mark_trust_use_sink(env)


def _rehome_wms_structure(env):
    """Re-home WMS storage locations that sit OUTSIDE the warehouse stock tree.

    The defect this repairs: the trust's storage structure (zones -> racks ->
    shelves -> compartments -> slots, plus bulk floors) was built under a
    branded top-level location "Dakshin Vrindavan" that had no parent, instead
    of under the warehouse's own ``lot_stock_id`` (WH/Stock). Stock stored
    there is perfectly real and Scan Issue finds it — the FEFO planner carries
    an explicit fallback for exactly this shape — but every report that scopes
    to the warehouse storage tree silently SKIPPED all of it:

      * the weekly audit generated no count line for those slots, so a whole
        floor of stock was never physically verified;
      * the stock-value report under-reported the trust's holdings.

    A silent omission in a counting system is worse than an error, so the
    structure is moved inside the warehouse tree, where every consumer agrees
    on what "in the warehouse" means. Only the PARENT LINK changes: no stock
    moves, no quant is touched, nothing is renamed, and each location keeps
    its identity, barcode and history.

    Multi-warehouse safety: with more than one warehouse there is no way to
    guess which one owns a stray tree, so the repair reports and does nothing.
    ARCHIVED warehouses count here: their storage is still theirs, and silently
    re-parenting it under the surviving warehouse would move a whole tree to
    the wrong owner.
    """
    Loc = env["stock.location"].with_context(active_test=False)
    warehouses = env["stock.warehouse"].with_context(active_test=False).search([])
    if len(warehouses) != 1:
        _logger.info(
            "wms_location: %d warehouse(s) found — skipping the storage-tree "
            "re-home (cannot infer the owning warehouse).",
            len(warehouses),
        )
        return env["stock.location"]
    stock = warehouses.lot_stock_id
    if not stock:
        return env["stock.location"]
    # active_test=False throughout: an ARCHIVED stray is still a stray. Leaving
    # it behind would leave the self-diagnostics probe permanently red, and the
    # day someone un-archives it the audit blind spot is back.
    inside = Loc.search([("id", "child_of", stock.id)]).ids
    strays = Loc.search(
        [
            ("wms_location_type", "in", _WMS_STRUCTURAL_TYPES),
            ("id", "not in", inside),
        ]
    )
    if not strays:
        return strays

    # Move only the OUTERMOST stray of each tree; everything below rides along
    # with its parent, so the internal shape is preserved and parent_path is
    # rewritten once per tree instead of once per location.
    #
    # "Outermost" must be judged on ANCESTRY, not on the immediate parent. With
    # an untyped location in the middle — zone -> (untyped area) -> rack — the
    # rack's direct parent is not itself a stray, so an immediate-parent test
    # would call the rack a top and re-parent it straight to WH/Stock, RIPPING
    # IT OUT of its own zone. The tree would end up inside the warehouse but
    # flattened, which is a different kind of wrong.
    stray_ids = set(strays.ids)

    def _has_stray_ancestor(loc):
        ancestors = (loc.parent_path or "").strip("/").split("/")[:-1]
        return any(int(a) in stray_ids for a in ancestors if a)

    tops = strays.filtered(lambda loc: not _has_stray_ancestor(loc))
    moved = Loc.browse()
    orphaned_parents = Loc.browse()
    for top in tops:
        parent = top.location_id
        # One savepoint per tree. A single unmovable tree must NOT abort the
        # upgrade: re-parenting an orphan SLOT straight onto WH/Stock, say,
        # trips _check_hierarchy ("a slot's parent must be a Compartment"),
        # and an exception here would roll back the whole migration and leave
        # the live database un-upgraded. Skip that tree, log it loudly, and
        # let the self-diagnostics probe keep flagging it.
        try:
            with env.cr.savepoint():
                top.location_id = stock.id
                env.flush_all()
        except Exception as exc:  # noqa: BLE001 - one bad tree must not stop the rest
            _logger.warning(
                "wms_location: could not re-home %s (%s) — left where it is: %s",
                top.display_name,
                top.wms_location_type,
                exc,
            )
            continue
        moved |= top
        if parent:
            orphaned_parents |= parent
    if not moved:
        return moved
    _logger.info("wms_location: re-homed %d tree(s) under %s.", len(moved), stock.complete_name)

    # Tidy up the branded shell they hung from — ARCHIVE, never delete. A
    # delete cascades: stock.putaway.rule rows pointing at it disappear
    # silently, and archived children (invisible to .child_ids) would be
    # dragged along with it. Archiving is reversible and loses nothing.
    Quant = env["stock.quant"]
    for parent in orphaned_parents:
        still_used = (
            parent.with_context(active_test=False).child_ids
            or parent.wms_location_type
            or Quant.with_context(active_test=False).search_count([("location_id", "=", parent.id)])
            or env["stock.putaway.rule"]
            .with_context(active_test=False)
            .search_count(
                ["|", ("location_in_id", "=", parent.id), ("location_out_id", "=", parent.id)]
            )
        )
        if not still_used and parent.active:
            _logger.info("wms_location: archiving the now-empty shell %s.", parent.complete_name)
            parent.active = False
    return moved

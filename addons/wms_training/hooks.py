# -*- coding: utf-8 -*-
"""STEP 7 visual-learning enrichment — shared, idempotent, Markup-safe.

Appends a "Visual guide" block (a workflow diagram + an annotated screen-map for
the scan wizards + a one-click deep-link to the real screen + a video-slot note)
to the major Help Center articles.

Called from BOTH:
  * post_init_hook(env)  -> fresh install
  * migrations/.../post-migrate.py -> upgrade of an existing database

so the visuals are present whether the module is installed clean or upgraded.

Idempotent: any previously-applied block (proper OR a mis-escaped earlier one)
is stripped before the correct block is appended. It only APPENDS — it never
rewrites the admin-authored article text.
"""
import logging
import re

from markupsafe import Markup

_logger = logging.getLogger(__name__)

MARKER = "data-wms-visual"

# slug -> (diagram filename, max-width px, action xmlid or None, alt text)
PLAN = {
    "workflow-receiving-stock": (
        "receiving.svg",
        340,
        "wms_barcode.action_wms_scan_receipt",
        "Receiving flow",
    ),
    "workflow-putaway-moving-stock-to-its-spot": (
        "putaway.svg",
        340,
        "wms_barcode.action_wms_scan_receipt",
        "Putaway flow",
    ),
    "workflow-fifo-issuing": (
        "fifo-issue.svg",
        340,
        "wms_barcode.action_wms_scan_issue",
        "FIFO issue flow",
    ),
    "workflow-returns": ("returns.svg", 540, "wms_barcode.action_wms_scan_return", "Returns flow"),
    "workflow-cycle-count-checking": (
        "cycle-count-audit.svg",
        340,
        "wms_reports.action_wms_audit",
        "Cycle count / audit flow",
    ),
    "workflow-creating-zones-and-floor-areas": (
        "warehouse-structure.svg",
        340,
        "wms_location.action_wms_zone_generator",
        "Warehouse structure",
    ),
    "workflow-creating-racks": (
        "warehouse-structure.svg",
        340,
        "wms_location.action_wms_rack_generator",
        "Warehouse structure",
    ),
    "workflow-assigning-slots": (
        "warehouse-structure.svg",
        340,
        "wms_location.action_wms_slots",
        "Warehouse structure",
    ),
    "workflow-damage-handling": (
        "damage-repair.svg",
        540,
        "wms_repair_damage.action_wms_damage",
        "Damage to repair flow",
    ),
    "workflow-repairs": (
        "damage-repair.svg",
        540,
        "wms_repair_damage.action_wms_repair",
        "Damage to repair flow",
    ),
    "workflow-backup-verification": (
        "backup-restore-health.svg",
        340,
        "wms_reports.action_wms_backup_audit",
        "Backup / restore / health flow",
    ),
    "workflow-restore-drill": (
        "backup-restore-health.svg",
        340,
        "wms_reports.action_wms_backup_audit",
        "Backup / restore / health flow",
    ),
    "workflow-using-reports": (
        "forecast-reorder.svg",
        340,
        "wms_reports.action_wms_occupancy",
        "Forecast and reorder flow",
    ),
    "workflow-low-stock-handling": (
        "forecast-reorder.svg",
        340,
        "wms_reports.action_wms_low_stock_alerts",
        "Forecast and reorder flow",
    ),
    "welcome": ("warehouse-structure.svg", 340, None, "Warehouse structure"),
    "admin-path-system-overview": ("roles-permissions.svg", 600, None, "Roles and permissions"),
    "keeper-path-getting-started": (
        "receiving.svg",
        340,
        "wms_barcode.action_wms_scan_receipt",
        "Receiving flow",
    ),
    "readonly-path-what-you-can-do": (
        "forecast-reorder.svg",
        340,
        "wms_reports.action_wms_occupancy",
        "Reports overview",
    ),
    "what-is-fifo": ("fifo-vs-fefo.svg", 520, None, "FIFO vs FEFO"),
    "what-is-fefo": ("fifo-vs-fefo.svg", 520, None, "FIFO vs FEFO"),
    "what-is-a-rack": ("warehouse-structure.svg", 340, None, "Warehouse structure"),
    "what-is-a-slot": ("warehouse-structure.svg", 340, None, "Warehouse structure"),
    "what-is-a-compartment": ("warehouse-structure.svg", 340, None, "Warehouse structure"),
    "what-is-a-zone": ("warehouse-structure.svg", 340, None, "Warehouse structure"),
}

# slug -> (annotated screen-map filename, caption) for the scan wizards
ANNOTATED = {
    "workflow-receiving-stock": ("scan-receipt.svg", "Scan Receipt — every field explained"),
    "workflow-fifo-issuing": ("scan-issue.svg", "Scan Issue — every field explained"),
    "workflow-returns": ("scan-return.svg", "Scan Return — every field explained"),
}

_IMG = (
    '<p style="text-align:center">'
    '<img src="/wms_training/static/img/diagrams/{f}" alt="{alt}" '
    'style="width:100%;max-width:{w}px;height:auto;border:1px solid #e5e7eb;'
    'border-radius:8px;padding:6px"/></p>'
)
_ANNO = (
    '<p style="text-align:center">'
    '<img src="/wms_training/static/img/annotated/{f}" alt="{alt}" '
    'style="width:100%;max-width:560px;height:auto;border:1px solid #e5e7eb;'
    'border-radius:8px;padding:6px"/><br/>'
    '<span class="text-muted" style="font-size:12px">{alt}</span></p>'
)
_BTN = (
    '<p style="text-align:center">'
    '<a href="/odoo/action-{aid}" class="btn btn-primary" target="_self">'
    "Open this screen in the app &#8594;</a></p>"
)
_NOTE = (
    '<p class="text-muted">&#9654; A short training video for this topic can be '
    "added here &#8212; open this article and use the <b>Training video</b> field "
    "(see the Recording Kit).</p>"
)

# start markers of a previously-applied block (proper or mis-escaped)
_BLOCK_STARTS = (
    "<hr/><div " + MARKER,
    "<hr><div " + MARKER,
    "&lt;hr/&gt;&lt;div " + MARKER,
    "&lt;hr&gt;&lt;div " + MARKER,
)


def _strip_prior(body):
    """Return the article body with any earlier visual block removed."""
    for needle in _BLOCK_STARTS:
        idx = body.find(needle)
        if idx != -1:
            return body[:idx]
    return body


def _build_block(env, slug, fname, width, action_xmlid, alt):
    button = ""
    if action_xmlid:
        act = env.ref(action_xmlid, raise_if_not_found=False)
        if act:
            button = _BTN.format(aid=act.id)
    anno = ""
    if slug in ANNOTATED:
        afile, acap = ANNOTATED[slug]
        anno = _ANNO.format(f=afile, alt=acap)
    return (
        "<hr/><div " + MARKER + '="1">'
        "<h3>&#128202; Visual guide</h3>"
        + _IMG.format(f=fname, w=width, alt=alt)
        + anno
        + button
        + _NOTE
        + "</div>"
    )


def apply_visual_enrichment(env):
    """Append (or refresh) the Visual guide block on each planned article."""
    Article = env["wms.help.article"]
    enriched = missing = 0
    for slug, (fname, width, action_xmlid, alt) in PLAN.items():
        art = Article.search([("slug", "=", slug)], limit=1)
        if not art:
            missing += 1
            continue
        clean = _strip_prior(art.body or "")
        block = _build_block(env, slug, fname, width, action_xmlid, alt)
        # Both operands are Markup, so the HTML is NOT escaped on concat; the
        # Html field still sanitizes on write (keeps the safe tag set).
        art.body = Markup(clean) + Markup(block)
        enriched += 1
    _logger.info(
        "STEP7 visual enrichment: %s articles enriched, %s slugs missing",
        enriched,
        missing,
    )
    return enriched


def apply_tour_action_links(env):
    """Resolve /odoo/action-PENDING-<xmlid> placeholders in the guided-tour
    articles to live /odoo/action-<id> links (Critical #6).

    Numeric action ids are DB-specific and break on a fresh install; the tours
    carry xmlid placeholders that this resolves at install/upgrade. Idempotent:
    only rewrites bodies that still contain a placeholder.
    """
    token = re.compile(r"/odoo/action-PENDING-([\w.]+)")

    def _resolve(match):
        act = env.ref(match.group(1), raise_if_not_found=False)
        return ("/odoo/action-%d" % act.id) if act else match.group(0)

    arts = env["wms.help.article"].search([("body", "like", "/odoo/action-PENDING-")])
    fixed = 0
    for art in arts:
        new_body = token.sub(_resolve, art.body or "")
        if new_body != (art.body or ""):
            art.body = new_body
            fixed += 1
    _logger.info("Critical #6: resolved guided-tour action links on %s article(s)", fixed)
    return fixed


def post_init_hook(env):
    """Fresh install: apply visual enrichment + resolve guided-tour links."""
    apply_visual_enrichment(env)
    apply_tour_action_links(env)

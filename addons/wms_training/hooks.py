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

# --- Google Drive backup training updates (19.0.1.8.0) ----------------------
# help_articles.xml / guided_tours.xml are noupdate="1": fresh installs get
# these changes from the edited XML, existing databases get them from the
# migration that calls apply_cloud_backup_training() below.

# Idempotency marker: present once the admin-tour cloud step has been added.
CLOUD_TOUR_MARKER = "Cloud safety net"

# Must mirror the step added to help_tour_admin in data/guided_tours.xml.
# Carries an action-PENDING placeholder: call apply_tour_action_links()
# AFTER inserting so the link resolves on the target database.
CLOUD_TOUR_STEP = (
    '<p style="text-align:center">'
    '<img src="/wms_training/static/img/diagrams/cloud-backup.svg" '
    'alt="Cloud backup: encrypted copy to Google Drive and the restore path back" '
    'style="width:100%;max-width:340px;height:auto;border:1px solid #e5e7eb;'
    'border-radius:8px;padding:6px"/></p>'
    '<ol start="7">'
    "<li><b>Cloud safety net</b> &#8212; every daily backup also lands in the "
    "trust's Google Drive, already encrypted. Run an extra one any time with "
    "<b>Back Up Now</b>; the schedule and tests live under "
    "<b>Configuration &#8594; Google Drive Backup</b>.<br/>"
    '<a href="/odoo/action-PENDING-wms_reports.action_wms_gdrive_backup_now" '
    'class="btn btn-primary btn-sm" target="_self">Open this screen &#8594;</a></li>'
    "</ol>"
)

# --- Offline-queue / Disaster-Recovery training updates (19.0.1.9.0) --------
# guided_tours.xml is noupdate="1" and is NOT edited for this feature, so BOTH
# fresh installs and upgrades get the admin-tour step from the hook below
# (apply_offline_queue_training is called from post_init_hook AND the
# 19.0.1.9.0 migration). The NEW offline-queue help article ships in
# help_articles.xml and needs no hook (new records load even under noupdate=1).

# Idempotency marker: present once the admin-tour Disaster-Recovery step exists.
DR_TOUR_MARKER = "Disaster Recovery page"

# Admin-tour step 8, inserted after the step-7 "Cloud safety net" list. Carries
# an action-PENDING placeholder for the manager-only DR page; call
# apply_tour_action_links() AFTER inserting so the link resolves on the target
# database.
DR_TOUR_STEP = (
    '<ol start="8">'
    "<li><b>Disaster Recovery page</b> &#8212; the manager-only console for the "
    "cloud tier. See Drive connection status, validate the backup folder, and "
    "watch the <b>offline upload queue</b> (anything waiting for internet, plus "
    "a <b>Retry Now</b> button). If the line is ever down, backups queue here "
    "and upload themselves when it returns &#8212; nothing is lost. It lives "
    "under <b>Configuration &#8594; Backup &amp; Disaster Recovery</b>.<br/>"
    '<a href="/odoo/action-PENDING-wms_reports.action_wms_gdrive_settings" '
    'class="btn btn-primary btn-sm" target="_self">Open this screen &#8594;</a></li>'
    "</ol>"
)

# --- Gaushala issue-dimensions / approvals training updates (19.0.1.10.0) ---
# guided_tours.xml is noupdate="1" and is NOT edited for the F1-F6 features, so
# BOTH fresh installs and upgrades get the admin-tour step from the hook below
# (apply_issue_dimensions_training is called from post_init_hook AND the
# 19.0.1.10.0 migration). It appends step 9 right after the step-8 "Disaster
# Recovery page" list. The NEW Department/Returns/Approvals help articles ship
# in help_articles.xml and need no hook (new records load even under
# noupdate=1).

# Idempotency marker: present once the admin-tour issue-dimensions step exists.
ISSUE_DIM_TOUR_MARKER = "Issue dimensions and approvals"

# Admin-tour step 9, inserted after the step-8 "Disaster Recovery page" list.
# Carries TWO action-PENDING placeholders (the Scan Issue screen that now shows
# the Department field, and the manager-only Approvals queue); call
# apply_tour_action_links() AFTER inserting so the links resolve on the target
# database.
ISSUE_DIM_TOUR_STEP = (
    '<ol start="9">'
    "<li><b>Issue dimensions and approvals</b> &#8212; every Scan Issue now "
    "captures a <b>Department</b> (Gaushala / Cowshed, Veterinary Hospital, "
    "Dairy, Kitchen, Temple / Pooja, and so on), a <b>Purpose</b>, and an "
    "optional <b>Animal / Cow</b>, so the Consumption Value report splits "
    "spend by department. The Department list lives under "
    "<b>Configuration &#8594; Departments</b> (manager-only). Two rules can "
    "hold an issue for your sign-off &#8212; a too-soon re-request of the same "
    "item (minimum-life guard) and a high-value issue (default Rs 5,000) "
    "&#8212; and held issues queue under <b>Operations &#8594; Approvals</b>, "
    "a manager-only menu where you Approve (re-checks stock, then issues) or "
    "Reject. Keepers can see a pending request but never self-approve.<br/>"
    '<a href="/odoo/action-PENDING-wms_barcode.action_wms_scan_issue" '
    'class="btn btn-primary btn-sm" target="_self">Open Scan Issue &#8594;</a> '
    '<a href="/odoo/action-PENDING-wms_barcode.action_wms_issue_approval" '
    'class="btn btn-primary btn-sm" target="_self">Open Approvals &#8594;</a></li>'
    "</ol>"
)

# slug -> [(old text, new text)] — the daily backup moved from "nightly /
# around 2am" to 4:30 PM when the Google Drive stage landed. Pure-text
# replacements (no tags), so the Html sanitizer cannot have altered them.
TIME_WORDING_FIXES = {
    "what-is-a-backup": [
        (
            "Because an encrypted backup ran the night before",
            "Because an encrypted backup ran the previous afternoon",
        )
    ],
    "what-is-a-health-check": [
        (
            "Last night's backup didn't run",
            "Yesterday's 4:30 PM backup didn't run",
        )
    ],
    "admin-path-backups-and-restore-drill": [
        (
            "Windows Task Scheduler, around 2am",
            "Windows Task Scheduler, every afternoon at 4:30 PM",
        )
    ],
    "workflow-backup-verification": [
        (
            "sees last night's database backup ticked green",
            "sees yesterday afternoon's database backup ticked green",
        )
    ],
    "workflow-restore-drill": [
        (
            "restores last night's backup",
            "restores the newest backup",
        )
    ],
}


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
        art.body = Markup(clean) + Markup(block)  # nosec B704 — Odoo sanitizes Html field on write
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


def apply_cloud_backup_training(env):
    """Apply the Google Drive training edits to an EXISTING database.

    Fresh installs already carry them in the (noupdate="1") XML; this brings
    upgraded databases to the same state:

    1. Re-word the stale backup-time mentions (the daily backup default
       moved from "nightly / around 2am" to 4:30 PM).
    2. Insert admin-tour step 7 "Cloud safety net" (Back Up Now) after the
       step-6 list.

    Idempotent: each replacement no-ops once applied; the tour step is
    skipped when its marker is already present. Call
    apply_tour_action_links() afterwards so the step's action-PENDING
    placeholder resolves. (The NEW cloud-backup help articles need no
    handling here — new records load on upgrade even under noupdate="1".)
    """
    Article = env["wms.help.article"]
    reworded = 0
    for slug, fixes in TIME_WORDING_FIXES.items():
        art = Article.search([("slug", "=", slug)], limit=1)
        if not art:
            continue
        body = str(art.body or "")
        new_body = body
        for old, new in fixes:
            new_body = new_body.replace(old, new)
        if new_body != body:
            art.body = new_body
            reworded += 1

    inserted = False
    tour = Article.search([("slug", "=", "tour-admin")], limit=1)
    if tour and CLOUD_TOUR_MARKER not in str(tour.body or ""):
        body = str(tour.body or "")
        anchor = body.find('<ol start="6"')
        close = body.find("</ol>", anchor) if anchor != -1 else -1
        if close != -1:
            pos = close + len("</ol>")
            tour.body = body[:pos] + CLOUD_TOUR_STEP + body[pos:]
            inserted = True
        else:
            _logger.warning(
                "cloud-backup training: admin tour found but no step-6 list "
                "anchor - tour step NOT inserted"
            )
    _logger.info(
        "cloud-backup training: %s article(s) re-worded, tour step inserted: %s",
        reworded,
        inserted,
    )
    return reworded


def apply_offline_queue_training(env):
    """Insert the admin-tour "Disaster Recovery page" step (19.0.1.9.0).

    guided_tours.xml is noupdate="1" and is not edited for the offline-queue
    feature, so this hook adds the step on BOTH fresh installs (via
    post_init_hook) and upgrades (via migrations/19.0.1.9.0/post-migrate.py).
    It appends step 8 right after the step-7 "Cloud safety net" list.

    Idempotent: skipped once its marker is present. Call
    apply_tour_action_links() afterwards so the step's action-PENDING
    placeholder resolves. (The NEW offline-queue help article needs no handling
    here — new records load on upgrade even under noupdate="1".)
    """
    Article = env["wms.help.article"]
    inserted = False
    tour = Article.search([("slug", "=", "tour-admin")], limit=1)
    if tour and DR_TOUR_MARKER not in str(tour.body or ""):
        body = str(tour.body or "")
        anchor = body.find('<ol start="7"')
        close = body.find("</ol>", anchor) if anchor != -1 else -1
        if close != -1:
            pos = close + len("</ol>")
            tour.body = body[:pos] + DR_TOUR_STEP + body[pos:]
            inserted = True
        else:
            _logger.warning(
                "offline-queue training: admin tour found but no step-7 list "
                "anchor - DR tour step NOT inserted"
            )
    _logger.info("offline-queue training: DR tour step inserted: %s", inserted)
    return inserted


def apply_issue_dimensions_training(env):
    """Insert the admin-tour "Issue dimensions and approvals" step (19.0.1.10.0).

    guided_tours.xml is noupdate="1" and is not edited for the F1-F6 gaushala
    features, so this hook adds the step on BOTH fresh installs (via
    post_init_hook) and upgrades (via migrations/19.0.1.10.0/post-migrate.py).
    It appends step 9 right after the step-8 "Disaster Recovery page" list.

    Idempotent: skipped once its marker is present. Call
    apply_tour_action_links() afterwards so the step's two action-PENDING
    placeholders resolve. (The NEW Department / Returns / Approvals help
    articles need no handling here — new records load on upgrade even under
    noupdate="1".)
    """
    Article = env["wms.help.article"]
    inserted = False
    tour = Article.search([("slug", "=", "tour-admin")], limit=1)
    if tour and ISSUE_DIM_TOUR_MARKER not in str(tour.body or ""):
        body = str(tour.body or "")
        anchor = body.find('<ol start="8"')
        close = body.find("</ol>", anchor) if anchor != -1 else -1
        if close != -1:
            pos = close + len("</ol>")
            tour.body = body[:pos] + ISSUE_DIM_TOUR_STEP + body[pos:]
            inserted = True
        else:
            _logger.warning(
                "issue-dimensions training: admin tour found but no step-8 list "
                "anchor - issue-dimensions tour step NOT inserted"
            )
    _logger.info("issue-dimensions training: tour step inserted: %s", inserted)
    return inserted


def post_init_hook(env):
    """Fresh install: apply visual enrichment + the offline-queue DR tour step +
    the gaushala issue-dimensions tour step, then resolve guided-tour links.

    The cloud-backup tour step (start=7) ships in guided_tours.xml for fresh
    installs, so apply_offline_queue_training finds its anchor; that adds the
    step-8 DR list, which apply_issue_dimensions_training then anchors to. On
    upgrades the migration calls apply_cloud_backup_training first.
    """
    apply_visual_enrichment(env)
    apply_offline_queue_training(env)
    apply_issue_dimensions_training(env)
    apply_tour_action_links(env)

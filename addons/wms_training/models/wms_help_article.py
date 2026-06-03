# -*- coding: utf-8 -*-
"""In-app Help Center article — the searchable knowledge base that powers
beginner onboarding, the terminology dictionary, role training paths,
workflow tutorials, FAQs, troubleshooting, and safety notes.

Deliberately simple: one model, no workflow, manager-editable, readable by
every internal user. Content is seeded from data/help_articles.xml and can
be extended in-app by a manager without a code change — that is the
long-term maintainability story.
"""
import re

from markupsafe import Markup
from odoo import api, fields, models

# Strict id extractors for the only two external hosts we embed. We pull
# ONLY the id (no other part of the URL is ever reflected into markup), so
# the rebuilt embed URL cannot carry an injection even though the player
# HTML is rendered with sanitize=False.
_YOUTUBE_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)")

CATEGORY_SELECTION = [
    ("terminology", "What is this? (terminology)"),
    ("role", "Role training"),
    ("workflow", "Workflow tutorial"),
    ("faq", "FAQ"),
    ("troubleshooting", "Troubleshooting"),
    ("safety", "Safety warning"),
]

AUDIENCE_SELECTION = [
    ("all", "Everyone"),
    ("admin", "Admin / Manager"),
    ("keeper", "Store Keeper"),
    ("readonly", "Read-only viewer"),
]


class WmsHelpArticle(models.Model):
    _name = "wms.help.article"
    _description = "WMS Help Center article"
    _order = "category, sequence, name"

    name = fields.Char(string="Title", required=True, translate=True, index=True)
    slug = fields.Char(
        required=True,
        index=True,
        help="Stable id used to deep-link an article (e.g. from a tooltip).",
    )
    category = fields.Selection(CATEGORY_SELECTION, required=True, index=True)
    audience = fields.Selection(
        AUDIENCE_SELECTION,
        default="all",
        required=True,
        index=True,
        help="Which role this article is written for. 'Everyone' always shows.",
    )
    body = fields.Html(
        string="Content",
        sanitize=True,
        help="Beginner-friendly explanation. Plain language, short, with a "
        "real warehouse example where it helps.",
    )
    keywords = fields.Char(help="Extra search terms a beginner might type.")
    sequence = fields.Integer(default=10)
    is_onboarding = fields.Boolean(
        string="Show in Getting Started",
        help="Tick to surface this article on the Welcome / Getting Started screen.",
    )
    active = fields.Boolean(default=True)

    # ---- Optional training video ----------------------------------------
    video_file = fields.Binary(
        string="Training video (upload)",
        attachment=True,
        help="Upload a short clip. Recommended: H.264 MP4, 720p, under 5 "
        "minutes, under 50 MB. Stored in Odoo and captured by the backup "
        "script; plays inline and works offline on a tablet. Takes "
        "priority over the link below.",
    )
    video_filename = fields.Char(string="Video filename")
    video_url = fields.Char(
        string="Video link (YouTube / Vimeo)",
        help="Optional: paste a YouTube or Vimeo link instead of uploading. "
        "Used only when no video is uploaded above. Needs internet to play.",
    )
    video_caption = fields.Char(
        string="Video caption",
        help="One line shown under the player, e.g. 'Scanning a receipt — 2 min'.",
    )
    has_video = fields.Boolean(
        compute="_compute_has_video",
        store=True,
        help="True when this article has an uploaded clip or a video link.",
    )
    video_player_html = fields.Html(
        string="Video",
        compute="_compute_video_player_html",
        # Safe: the markup is built entirely server-side from validated
        # inputs (an attachment id, or a strict id extracted from a
        # whitelisted host). No raw user HTML is ever reflected.
        sanitize=False,
        readonly=True,
    )

    _slug_unique = models.Constraint(
        "UNIQUE(slug)",
        "Each help article needs a unique slug.",
    )

    @api.depends("video_file", "video_url")
    def _compute_has_video(self):
        for rec in self:
            rec.has_video = bool(rec.video_file or rec.video_url)

    def _safe_embed(self, url):
        """Return sanitized markup for a video LINK.

        YouTube / Vimeo → a whitelisted iframe built from a strict id we
        extract ourselves (never the raw URL). Any other host → a plain
        external link (we don't embed arbitrary origins). Returns Markup.
        """
        url = (url or "").strip()
        if not url:
            return Markup("")
        m = _YOUTUBE_RE.search(url)
        if m:
            return Markup(
                '<div class="ratio ratio-16x9" style="max-width:720px">'
                '<iframe src="https://www.youtube-nocookie.com/embed/{vid}" '
                'title="Training video" frameborder="0" loading="lazy" '
                'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                'gyroscope; picture-in-picture" allowfullscreen></iframe></div>'
            ).format(vid=m.group(1))
        m = _VIMEO_RE.search(url)
        if m:
            return Markup(
                '<div class="ratio ratio-16x9" style="max-width:720px">'
                '<iframe src="https://player.vimeo.com/video/{vid}" '
                'title="Training video" frameborder="0" loading="lazy" '
                'allow="autoplay; fullscreen; picture-in-picture" '
                "allowfullscreen></iframe></div>"
            ).format(vid=m.group(1))
        # Unknown host: do NOT embed — offer a safe outbound link instead.
        return Markup(
            '<p><a href="{url}" target="_blank" rel="noopener noreferrer">'
            "▶ Watch the training video (opens in a new tab)</a></p>"
        ).format(url=url)

    @api.depends("video_file", "video_url", "video_caption")
    def _compute_video_player_html(self):
        for rec in self:
            html = Markup("")
            if rec.video_file and rec.id:
                # Stream the uploaded clip from the binary field. /web/content
                # checks read access on the record, so only internal users
                # (who can read help articles) can fetch it.
                base = "/web/content/wms.help.article/{rid}/video_file".format(rid=rec.id)
                src = base + "?download=false"
                dl = base + "?download=true"
                html = Markup(
                    '<video controls playsinline preload="metadata" '
                    'style="width:100%;max-width:720px;border-radius:8px">'
                    '<source src="{src}"/>'
                    "Your browser can't play this video inline. "
                    '<a href="{dl}">Download it instead.</a>'
                    "</video>"
                ).format(src=src, dl=dl)
            elif rec.video_url:
                html = rec._safe_embed(rec.video_url)
            if html and rec.video_caption:
                html = html + Markup('<p class="text-muted small mt-1">{cap}</p>').format(
                    cap=rec.video_caption
                )
            rec.video_player_html = html or False

    @api.model
    def _category_icon(self, category):
        return {
            "terminology": "fa-book",
            "role": "fa-graduation-cap",
            "workflow": "fa-list-ol",
            "faq": "fa-question-circle",
            "troubleshooting": "fa-wrench",
            "safety": "fa-exclamation-triangle",
        }.get(category, "fa-info-circle")

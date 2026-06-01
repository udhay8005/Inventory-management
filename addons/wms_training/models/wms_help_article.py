# -*- coding: utf-8 -*-
"""In-app Help Center article — the searchable knowledge base that powers
beginner onboarding, the terminology dictionary, role training paths,
workflow tutorials, FAQs, troubleshooting, and safety notes.

Deliberately simple: one model, no workflow, manager-editable, readable by
every internal user. Content is seeded from data/help_articles.xml and can
be extended in-app by a manager without a code change — that is the
long-term maintainability story.
"""
from odoo import api, fields, models

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

    _slug_unique = models.Constraint(
        "UNIQUE(slug)",
        "Each help article needs a unique slug.",
    )

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

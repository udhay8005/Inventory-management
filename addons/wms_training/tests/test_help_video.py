# -*- coding: utf-8 -*-
"""Tests for the training-video support on wms.help.article.

Proves the player markup is built correctly for an uploaded clip and for
whitelisted YouTube/Vimeo links, that has_video tracks state, and — most
importantly — that an untrusted link is NOT embedded as an iframe (no XSS
surface even though the player HTML is rendered with sanitize=False).
"""
import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_training")
class TestHelpVideo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Article = cls.env["wms.help.article"]

    def _mk(self, slug, **vals):
        base = {
            "slug": slug,
            "name": "vid " + slug,
            "category": "workflow",
            "audience": "all",
        }
        base.update(vals)
        return self.Article.create(base)

    def test_no_video_means_empty_player(self):
        a = self._mk("vt-none")
        self.assertFalse(a.has_video)
        self.assertFalse(a.video_player_html)

    def test_youtube_link_builds_whitelisted_iframe(self):
        a = self._mk("vt-yt", video_url="https://youtu.be/dQw4w9WgXcQ")
        self.assertTrue(a.has_video)
        html = str(a.video_player_html)
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ", html)
        self.assertIn("<iframe", html)

    def test_youtube_watch_url_form(self):
        a = self._mk("vt-yt2", video_url="https://www.youtube.com/watch?v=abc123XYZ_-")
        self.assertIn("youtube-nocookie.com/embed/abc123XYZ_-", str(a.video_player_html))

    def test_vimeo_link_builds_whitelisted_iframe(self):
        a = self._mk("vt-vimeo", video_url="https://vimeo.com/123456789")
        html = str(a.video_player_html)
        self.assertIn("player.vimeo.com/video/123456789", html)
        self.assertIn("<iframe", html)

    def test_untrusted_link_is_NOT_embedded(self):
        """A non-whitelisted host must render as a plain link, never an
        iframe — and any script-y junk must be escaped, not reflected."""
        evil = "https://evil.example.com/x?a=<script>alert(1)</script>"
        a = self._mk("vt-evil", video_url=evil)
        html = str(a.video_player_html)
        self.assertNotIn("<iframe", html, "untrusted host must not be iframed")
        self.assertNotIn("<script>", html, "raw script must be escaped")
        self.assertIn("&lt;script&gt;", html, "the link text should be HTML-escaped")

    def test_uploaded_clip_builds_video_tag(self):
        a = self._mk("vt-upload")
        a.write(
            {
                "video_file": base64.b64encode(b"\x00\x00\x00\x18ftypmp42fakeclip"),
                "video_filename": "demo.mp4",
            }
        )
        self.assertTrue(a.has_video)
        html = str(a.video_player_html)
        self.assertIn("<video", html)
        self.assertIn("/web/content/wms.help.article/%d/video_file" % a.id, html)

    def test_upload_takes_priority_over_link(self):
        a = self._mk("vt-both", video_url="https://youtu.be/dQw4w9WgXcQ")
        a.write({"video_file": base64.b64encode(b"clip"), "video_filename": "c.mp4"})
        html = str(a.video_player_html)
        self.assertIn("<video", html)
        self.assertNotIn("youtube-nocookie", html)

    def test_caption_appended(self):
        a = self._mk(
            "vt-cap",
            video_url="https://youtu.be/dQw4w9WgXcQ",
            video_caption="Scanning a receipt — 2 min",
        )
        self.assertIn("Scanning a receipt", str(a.video_player_html))

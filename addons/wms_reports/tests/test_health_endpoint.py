"""High - optional shared-secret gate on the public /wms/health endpoint.

Default (no token configured): the endpoint stays open so credential-less
monitoring keeps working. When an admin sets `wms_reports.health_token`, the
endpoint demands it - defense-in-depth if the host is ever network-exposed.
"""

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_health")
class TestHealthEndpointToken(HttpCase):
    def test_open_when_no_token_configured(self):
        self.env["ir.config_parameter"].sudo().set_param("wms_reports.health_token", "")
        r = self.url_open("/wms/health")
        self.assertIn(r.status_code, (200, 503), "open endpoint should answer with a health code")

    def test_token_required_when_configured(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "wms_reports.health_token", "s3cr3t-health"
        )
        # No token -> rejected.
        self.assertEqual(self.url_open("/wms/health").status_code, 401)
        # Correct token via query param -> back to a normal health code.
        self.assertIn(self.url_open("/wms/health?token=s3cr3t-health").status_code, (200, 503))
        # Wrong token -> rejected.
        self.assertEqual(self.url_open("/wms/health?token=nope").status_code, 401)

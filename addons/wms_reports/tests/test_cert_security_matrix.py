"""UI certification — controller route matrix per role (HTTP layer).

Complements the ORM menu-smoke: the act_url controllers re-check the group
in-method and return 404 to an unauthorised user. This asserts the gate holds
per role over real HTTP. Backup/restore routes are tested NEGATIVE-only (the
manager positive would stream a real DB dump).
"""

from odoo.tests import HttpCase, tagged

from ._cert_roles import CertRolesMixin


@tagged("post_install", "-at_install", "wms", "wms_ui_cert", "wms_cert_routes")
class TestCertRouteMatrix(CertRolesMixin, HttpCase):
    def _status(self, login, url):
        self.authenticate(login, login + "_pw")
        return self.url_open(url, timeout=30).status_code

    def test_dashboard_is_manager_only(self):
        self.assertEqual(
            self._status("cert_mgr", "/wms/dashboard"), 200, "manager reaches dashboard"
        )
        self.assertEqual(
            self._status("cert_keeper", "/wms/dashboard"),
            404,
            "keeper must NOT reach the dashboard",
        )
        self.assertEqual(
            self._status("cert_plain", "/wms/dashboard"), 404, "non-WMS user must NOT reach it"
        )

    def test_find_and_map_open_to_keepers_not_outsiders(self):
        for url in ("/wms/find", "/wms/warehouse/map"):
            self.assertEqual(self._status("cert_keeper", url), 200, "keeper must reach %s" % url)
            self.assertEqual(
                self._status("cert_plain", url), 404, "non-WMS user must NOT reach %s" % url
            )

    def test_backup_routes_refuse_keepers(self):
        # Negative only — exercising the manager path would stream a live dump.
        for url in ("/wms/admin/backup/download", "/wms/admin/restore/info"):
            self.assertEqual(
                self._status("cert_keeper", url), 404, "keeper must NOT reach %s" % url
            )

    def test_rack_grid_keepers_only(self):
        # /wms/rack/<id>/grid sudo()-reads stock, gated on group_wms_user — a
        # non-WMS user must not be able to enumerate a rack's stock.
        url = "/wms/rack/%d/grid" % self.cert_rack.id
        self.assertEqual(self._status("cert_keeper", url), 200, "keeper must reach the rack grid")
        self.assertEqual(
            self._status("cert_plain", url), 404, "a non-WMS user must NOT enumerate rack stock"
        )

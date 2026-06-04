"""Medium - the scan wizards must require the per-keeper capability group, not
just baseline group_wms_user. Previously the capability was enforced only by the
menu's groups=, so a keeper without it could still create receipts/issues over
RPC (moving stock + bypassing the roster gate)."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_acl")
class TestScanCapabilityAcl(TransactionCase):
    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "group_ids": [(6, 0, [self.env.ref(xmlid).id])],
            }
        )

    def _can_create(self, user, model):
        return (
            self.env["ir.model.access"]
            .with_user(user)
            .check(model, "create", raise_exception=False)
        )

    def test_receipt_requires_scan_receive_capability(self):
        base = self._user("wms_location.group_wms_user", "acl_base_rcv")
        cap = self._user("wms_location.group_wms_can_scan_receive", "acl_cap_rcv")
        self.assertFalse(self._can_create(base, "wms.scan.receipt"))
        self.assertTrue(self._can_create(cap, "wms.scan.receipt"))

    def test_issue_requires_scan_issue_capability(self):
        base = self._user("wms_location.group_wms_user", "acl_base_iss")
        cap = self._user("wms_location.group_wms_can_scan_issue", "acl_cap_iss")
        self.assertFalse(self._can_create(base, "wms.scan.issue"))
        self.assertTrue(self._can_create(cap, "wms.scan.issue"))

    def test_manager_keeps_full_scan_access(self):
        # group_wms_manager implies every capability, so a manager must retain
        # create access on both scan models after the tightening.
        mgr = self._user("wms_location.group_wms_manager", "acl_mgr")
        self.assertTrue(self._can_create(mgr, "wms.scan.receipt"))
        self.assertTrue(self._can_create(mgr, "wms.scan.issue"))

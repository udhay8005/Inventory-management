"""Medium - creating/submitting audits must require the submit-audit capability
group, not just baseline group_wms_user (audit lines are the count-of-record).
Previously the capability was menu-gated only, so a non-capability keeper could
create audits over RPC."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_acl")
class TestAuditCapabilityAcl(TransactionCase):
    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "group_ids": [(6, 0, [self.env.ref(xmlid).id])]}
        )

    def _can_create(self, user, model):
        return (
            self.env["ir.model.access"]
            .with_user(user)
            .check(model, "create", raise_exception=False)
        )

    def test_audit_requires_submit_audit_capability(self):
        base = self._user("wms_location.group_wms_user", "acl_aud_base")
        cap = self._user("wms_location.group_wms_can_submit_audit", "acl_aud_cap")
        mgr = self._user("wms_location.group_wms_manager", "acl_aud_mgr")
        for model in ("wms.audit", "wms.audit.line"):
            self.assertFalse(self._can_create(base, model), "%s baseline blocked" % model)
            self.assertTrue(self._can_create(cap, model), "%s capability allowed" % model)
            self.assertTrue(self._can_create(mgr, model), "%s manager allowed" % model)

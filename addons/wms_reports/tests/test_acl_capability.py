"""Medium - creating/submitting audits must require the submit-audit capability
group, not just baseline group_wms_user (audit lines are the count-of-record).
Previously the capability was menu-gated only, so a non-capability keeper could
create audits over RPC."""

from odoo.exceptions import AccessError
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


@tagged("post_install", "-at_install", "wms", "wms_acl")
class TestAuditDecisionManagerOnly(TransactionCase):
    """Accept/Reject must re-check the manager group in-method. A keeper holds
    write+create on wms.audit (they author and submit audits) and the buttons
    are only hidden in the view, so without the re-check a keeper could
    self-accept their own physical count over RPC and silently overwrite live
    stock — defeating the manager-review gate the audit workflow enforces."""

    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "group_ids": [(6, 0, [self.env.ref(xmlid).id])]}
        )

    def test_keeper_cannot_accept_or_reject_audit(self):
        keeper = self._user("wms_location.group_wms_can_submit_audit", "aud_keeper")
        mgr = self._user("wms_location.group_wms_manager", "aud_mgr_dec")
        slot = self.env.ref("stock.stock_location_stock")
        product = self.env["product.product"].create(
            {"name": "Aud Decide Probe", "is_storable": True}
        )
        self.env["stock.quant"]._update_available_quantity(product, slot, 10.0)
        audit = self.env["wms.audit"].create({"state": "submitted"})
        self.env["wms.audit.line"].create(
            {
                "audit_id": audit.id,
                "location_id": slot.id,
                "product_id": product.id,
                "expected_qty": 10.0,
                "counted_qty": 7.0,  # a variance the keeper would love to self-apply
            }
        )
        with self.assertRaises(AccessError):
            audit.with_user(keeper).action_review_accept()
        with self.assertRaises(AccessError):
            audit.with_user(keeper).action_reject()
        # The refused calls must not have advanced the workflow or touched stock.
        self.assertEqual(audit.state, "submitted")
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(product, slot),
            10.0,
            "a refused accept must not apply the variance",
        )
        # A real manager can still decide.
        audit.with_user(mgr).action_review_accept()
        self.assertEqual(audit.state, "reviewed")

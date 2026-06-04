"""Medium - filing damage must require the file-damage capability group, not
just baseline group_wms_user (damage events adjust on-hand). Previously the
capability was menu-gated only, so a non-capability keeper could file damage
over RPC."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "wms", "wms_acl")
class TestDamageCapabilityAcl(TransactionCase):
    def _user(self, xmlid, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "group_ids": [(6, 0, [self.env.ref(xmlid).id])]}
        )

    def _can_create(self, user):
        return (
            self.env["ir.model.access"]
            .with_user(user)
            .check("wms.damage", "create", raise_exception=False)
        )

    def test_damage_requires_file_damage_capability(self):
        base = self._user("wms_location.group_wms_user", "acl_dmg_base")
        cap = self._user("wms_location.group_wms_can_file_damage", "acl_dmg_cap")
        mgr = self._user("wms_location.group_wms_manager", "acl_dmg_mgr")
        self.assertFalse(self._can_create(base))
        self.assertTrue(self._can_create(cap))
        self.assertTrue(self._can_create(mgr), "manager implies file-damage")

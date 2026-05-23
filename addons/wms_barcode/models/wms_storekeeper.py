"""Store Keeper roster + their individual Odoo logins.

History
-------
v1 (original): wms.storekeeper was a *roster* of human names. A single
shared `storekeeper` Odoo account was logged in at the desk; the
on-duty human picked their roster name on every Scan Issue / Damage
form for audit purposes.

v2 (this file): each roster entry can OPTIONALLY get its own Odoo
login. The Admin fills `login` + `initial_password` on the form,
ticks the capability check-boxes for what the keeper is allowed to do,
and the system spins up a real res.users record linked back to the
roster entry. Existing shared-login deployments keep working because
user_id stays optional.

Capabilities granted via the form correspond 1:1 with the five
sub-groups defined in wms_location/security/wms_security.xml. The
checkboxes are stored proxies - the source of truth is res.users.group_ids
(so a manual edit via Settings -> Users stays in sync).
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


# Capability ↔ group xmlid map. Keep aligned with wms_security.xml.
_CAPABILITY_GROUPS = {
    "can_scan_receive":   "wms_location.group_wms_can_scan_receive",
    "can_scan_issue":     "wms_location.group_wms_can_scan_issue",
    "can_file_damage":    "wms_location.group_wms_can_file_damage",
    "can_submit_audit":   "wms_location.group_wms_can_submit_audit",
    "can_manage_catalog": "wms_location.group_wms_can_manage_catalog",
}


class WmsStorekeeper(models.Model):
    _name = "wms.storekeeper"
    _description = "Store Keeper roster entry"
    _order = "name"

    name = fields.Char(string="Name", required=True, index=True)
    phone = fields.Char(string="Phone")
    note = fields.Text(string="Notes")
    active = fields.Boolean(
        string="On the roster",
        default=True,
        help="Untick to retire a Store Keeper without deleting the "
        "historical issues that mention them. If a linked Odoo login "
        "exists, it is archived as well.",
    )

    # --- Optional Odoo login --------------------------------------------
    user_id = fields.Many2one(
        "res.users",
        string="Odoo login",
        index=True,
        ondelete="set null",
        help="The res.users record this human signs in with. Leave "
        "empty if this keeper uses the shared `storekeeper` desk login; "
        "set it to give them their own credentials.",
    )
    login = fields.Char(
        string="Login",
        help="Username for the Odoo login (e.g. 'suresh'). Click "
        "'Create login' to materialise it on res.users.",
    )
    email = fields.Char(string="Email")
    initial_password = fields.Char(
        string="Initial password",
        help="Used only when materialising the login for the first time. "
        "Cleared from this row after the user is created - the actual "
        "hash lives on res.users, never here.",
    )

    # --- Capability flags -----------------------------------------------
    # Stored=False so the source of truth stays res.users.group_ids.
    # The inverse method writes the matching group on/off when the
    # Admin ticks the checkbox.
    can_scan_receive = fields.Boolean(
        string="Can Scan Receipt / Return",
        compute="_compute_capabilities",
        inverse="_inverse_can_scan_receive",
        help="Shows the Scan Receipt + Scan Return menus and grants "
        "create on the wizard. Default ON for a new login.",
    )
    can_scan_issue = fields.Boolean(
        string="Can Scan Issue",
        compute="_compute_capabilities",
        inverse="_inverse_can_scan_issue",
        help="Shows the Scan Issue (FIFO) menu and grants create on "
        "the wizard. Default ON.",
    )
    can_file_damage = fields.Boolean(
        string="Can file Damage events",
        compute="_compute_capabilities",
        inverse="_inverse_can_file_damage",
        help="Allows opening the Damage form and submitting a damage "
        "report. The keeper still cannot create Repair Orders (Admin's "
        "job) but can flag items as damaged. Default ON.",
    )
    can_submit_audit = fields.Boolean(
        string="Can submit Inventory audits",
        compute="_compute_capabilities",
        inverse="_inverse_can_submit_audit",
        help="Lets the keeper open an audit, count slots, and submit "
        "the result to the Admin. Default ON.",
    )
    can_manage_catalog = fields.Boolean(
        string="Can manage Carton aliases + Labels",
        compute="_compute_capabilities",
        inverse="_inverse_can_manage_catalog",
        help="Edit the carton-barcode alias table + the thermal label "
        "profile. Default OFF - this is usually Admin work.",
    )

    has_login = fields.Boolean(
        string="Has Odoo login",
        compute="_compute_has_login",
        store=True,
        help="True when user_id is set. Drives the visibility of the "
        "'Create login' vs 'Open login' buttons on the form.",
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Each Store Keeper name must be unique on the roster.",
    )
    _user_unique = models.Constraint(
        "UNIQUE(user_id)",
        "An Odoo login can be tied to only one roster entry.",
    )

    # ---------------------------------------------------------------
    # Computed helpers
    # ---------------------------------------------------------------
    @api.depends("user_id")
    def _compute_has_login(self):
        for rec in self:
            rec.has_login = bool(rec.user_id)

    @api.depends("user_id", "user_id.group_ids")
    def _compute_capabilities(self):
        """Read the booleans from the linked res.users.group_ids."""
        for rec in self:
            if not rec.user_id:
                for cap in _CAPABILITY_GROUPS:
                    rec[cap] = False
                continue
            for cap, xmlid in _CAPABILITY_GROUPS.items():
                grp = self.env.ref(xmlid, raise_if_not_found=False)
                rec[cap] = bool(grp and grp in rec.user_id.group_ids)

    # Each inverse method writes one group on the linked user. They
    # all share the same logic - factored into _toggle_capability().
    def _toggle_capability(self, cap_xmlid, attr_name):
        grp = self.env.ref(cap_xmlid, raise_if_not_found=False)
        if not grp:
            return
        for rec in self:
            if not rec.user_id:
                # The Admin ticked a capability on a roster entry that
                # has no Odoo login yet. Defer - the booleans become
                # real the moment the login is materialised, and we
                # remember the choice via the form's recordset state.
                continue
            currently_has = grp in rec.user_id.group_ids
            should_have = bool(rec[attr_name])
            if should_have and not currently_has:
                rec.user_id.sudo().write({"group_ids": [(4, grp.id)]})
            elif currently_has and not should_have:
                rec.user_id.sudo().write({"group_ids": [(3, grp.id)]})

    def _inverse_can_scan_receive(self):
        self._toggle_capability(_CAPABILITY_GROUPS["can_scan_receive"], "can_scan_receive")

    def _inverse_can_scan_issue(self):
        self._toggle_capability(_CAPABILITY_GROUPS["can_scan_issue"], "can_scan_issue")

    def _inverse_can_file_damage(self):
        self._toggle_capability(_CAPABILITY_GROUPS["can_file_damage"], "can_file_damage")

    def _inverse_can_submit_audit(self):
        self._toggle_capability(_CAPABILITY_GROUPS["can_submit_audit"], "can_submit_audit")

    def _inverse_can_manage_catalog(self):
        self._toggle_capability(_CAPABILITY_GROUPS["can_manage_catalog"], "can_manage_catalog")

    # ---------------------------------------------------------------
    # 'Create login' button
    # ---------------------------------------------------------------
    def action_create_login(self):
        """Materialise res.users from the form's login + password.

        Defaults:
          * group_wms_user (the base role - read access + menu shell)
          * group_wms_can_scan_receive
          * group_wms_can_scan_issue
          * group_wms_can_file_damage
          * group_wms_can_submit_audit
          (mirrors the legacy shared-login behaviour)

        After create:
          * Clear initial_password from this row (the hashed version
            lives on res.users now)
          * The capability booleans re-read from res.users so they
            reflect the just-granted groups
        """
        Users = self.env["res.users"].sudo()
        base = self.env.ref("wms_location.group_wms_user")
        internal = self.env.ref("base.group_user")
        # Default capability grants. Manage Catalog stays OFF - it's
        # usually Admin work.
        default_caps = [
            self.env.ref("wms_location.group_wms_can_scan_receive"),
            self.env.ref("wms_location.group_wms_can_scan_issue"),
            self.env.ref("wms_location.group_wms_can_file_damage"),
            self.env.ref("wms_location.group_wms_can_submit_audit"),
        ]
        for rec in self:
            if rec.user_id:
                raise UserError(_(
                    "'%s' already has an Odoo login (%s). Edit the "
                    "capability check-boxes directly; the login itself "
                    "can be managed from Settings -> Users."
                ) % (rec.name, rec.user_id.login))
            if not rec.login:
                raise UserError(_(
                    "Pick a Login for '%s' before creating the user. "
                    "Use a short lowercase name (e.g. 'suresh', 'ramesh')."
                ) % rec.name)
            if not rec.initial_password:
                raise UserError(_(
                    "Set an Initial password so '%s' has something to "
                    "type on first login. They can change it themselves "
                    "afterwards under their user menu."
                ) % rec.name)

            # Check for login clash before create so the error is
            # friendly instead of a SQL UNIQUE violation.
            clash = Users.with_context(active_test=False).search(
                [("login", "=", rec.login)], limit=1,
            )
            if clash:
                raise UserError(_(
                    "Login %r is already taken (by %s). Pick another."
                ) % (rec.login, clash.name))

            user = Users.create({
                "name": rec.name,
                "login": rec.login,
                "password": rec.initial_password,
                "email": rec.email or False,
                "lang": "en_US",
                "notification_type": "inbox",
                "group_ids": [
                    (6, 0, [internal.id, base.id] + [g.id for g in default_caps]),
                ],
            })
            rec.write({
                "user_id": user.id,
                "initial_password": False,  # never persist plaintext
            })

    def action_open_login(self):
        """Quick-jump to the res.users record for further admin tasks
        (change password via 'Send Reset Password Email', archive, etc)."""
        self.ensure_one()
        if not self.user_id:
            raise UserError(_("This roster entry has no Odoo login yet."))
        return {
            "type": "ir.actions.act_window",
            "name": "Odoo user",
            "res_model": "res.users",
            "res_id": self.user_id.id,
            "view_mode": "form",
            "target": "current",
        }

    # ---------------------------------------------------------------
    # Archive cascades to the linked user
    # ---------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if "active" in vals:
            # Mirror the archived flag to the linked res.users so
            # archived keepers can't sneak past the lockdown.
            for rec in self:
                if rec.user_id:
                    rec.user_id.sudo().write({"active": rec.active})
        return res

    @api.constrains("login")
    def _check_login_no_whitespace(self):
        for rec in self:
            if rec.login and (rec.login != rec.login.strip() or " " in rec.login):
                raise ValidationError(_(
                    "Login %r contains whitespace. Use a short, "
                    "lowercase, single-word handle - e.g. 'suresh', "
                    "'ramesh_a'."
                ) % rec.login)

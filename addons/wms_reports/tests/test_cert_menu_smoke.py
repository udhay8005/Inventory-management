"""UI certification — per-role menu smoke (the backbone).

For every role, every menu the role can SEE must OPEN without error: each
act_window action's views render and the underlying model is readable. Plus the
visibility matrix: a baseline keeper must not see manager/config menus, and each
capability menu is hidden without its cap and shown with it.

ORM-level (no headless browser needed) so it runs fast and repeatably in the
fix loop. Controller (act_url) routes are certified in test_cert_security_matrix.
"""

from odoo.tests import TransactionCase, tagged

from ._cert_roles import CAPABILITY_MENUS, FORBIDDEN_FOR_BASELINE, CertRolesMixin


@tagged("post_install", "-at_install", "wms", "wms_ui_cert", "wms_cert_menu")
class TestCertMenuSmoke(CertRolesMixin, TransactionCase):
    def _menu_payload(self, user):
        return self.env["ir.ui.menu"].with_user(user).load_menus(False)

    def _visible_xmlids(self, user):
        return {
            m["xmlid"]
            for m in self._menu_payload(user).values()
            if isinstance(m, dict) and m.get("xmlid")
        }

    def _open_act_window_menus(self, user):
        """Render every view + ACL-check every act_window action the user sees.
        Returns ([(xmlid, error_str), ...], n_opened) — the error list plus how
        many actions were actually exercised (so 'all opened' can't pass
        vacuously when a role's visible menu set has collapsed to zero)."""
        errors = []
        opened = 0
        for m in self._menu_payload(user).values():
            if not isinstance(m, dict):
                continue
            if m.get("action_model") != "ir.actions.act_window" or not m.get("action_id"):
                continue
            xmlid = m.get("xmlid") or "(no xmlid)"
            try:
                action = self.env["ir.actions.act_window"].sudo().browse(m["action_id"])
                res_model = action.res_model
                if not res_model or res_model not in self.env:
                    continue
                Model = self.env[res_model].with_user(user)
                rendered_any = False
                for view in action.view_ids:
                    if view.view_mode in (
                        "list",
                        "form",
                        "kanban",
                        "pivot",
                        "graph",
                        "calendar",
                        "activity",
                    ):
                        Model.get_view(view.view_id.id, view.view_mode)
                        rendered_any = True
                if not rendered_any:
                    for vt in (action.view_mode or "list").split(","):
                        vt = vt.strip()
                        if vt and vt not in ("qweb",):
                            Model.get_view(False, vt)
                # ACL read — catches a visible menu the user cannot actually read
                # and SQL-view (_auto=False) CREATE/JOIN failures on open.
                Model.search([], limit=1)
                opened += 1
            except Exception as e:  # noqa: BLE001 — collect the offending menu + error
                errors.append((xmlid, "%s: %s" % (type(e).__name__, e)))
        return errors, opened

    def test_every_visible_menu_opens_for_each_role(self):
        problems = {}
        empty_roles = []
        # PORTAL is not a backend UI user — it cannot even read ir.ui.menu
        # (correct security). Its unreachability is certified over HTTP in
        # test_cert_security_matrix, not here.
        for code in [c for c in self.ALL_ROLES if c != "PORTAL"]:
            errs, opened = self._open_act_window_menus(self.role(code))
            if errs:
                problems[code] = errs
            # Every WMS-bearing role must actually exercise >0 menus, so the
            # "all opened" guarantee can't pass vacuously if a regression hid
            # every menu. PLAIN (internal, no WMS group) legitimately sees none.
            if code != "PLAIN" and opened == 0:
                empty_roles.append(code)
        self.assertFalse(
            problems,
            "Visible menus failed to open for some roles:\n"
            + "\n".join(
                "  [%s] %s" % (code, "; ".join("%s -> %s" % e for e in errs))
                for code, errs in problems.items()
            ),
        )
        self.assertFalse(
            empty_roles,
            "these WMS roles opened ZERO menus (vacuous-pass risk — a regression "
            "may have hidden their whole menu set): %s" % empty_roles,
        )

    def test_buyer_and_repair_role_boundaries(self):
        """Pin the two roles that otherwise ride only the generic loop."""
        buyer_visible = self._visible_xmlids(self.role("BUYER"))
        self.assertIn(
            "wms_ai_forecast.menu_wms_forecast_list",
            buyer_visible,
            "the Buyer must see the Forecast / reorder list",
        )
        # Repair Tech: by current design the Repair Orders menu is manager-only
        # (owner-decision flagged in the audit) — they reach repair orders via
        # the handed record — but they MUST be able to read wms.repair.order.
        repair = self.role("REPAIR")
        self.assertNotIn(
            "wms_repair_damage.menu_wms_repair",
            self._visible_xmlids(repair),
            "current design: Repair Orders menu is manager-only",
        )
        self.assertTrue(
            self.env["ir.model.access"]
            .with_user(repair)
            .check("wms.repair.order", "read", raise_exception=False),
            "a Repair Tech must be able to read repair orders",
        )

    def test_baseline_keeper_forbidden_menus_absent(self):
        visible = self._visible_xmlids(self.role("KEEPER_BASE"))
        leaked = [x for x in FORBIDDEN_FOR_BASELINE if x in visible]
        self.assertFalse(leaked, "baseline keeper must NOT see: %s" % leaked)

    def test_capability_menus_are_gated(self):
        baseline = self._visible_xmlids(self.role("KEEPER_BASE"))
        for menu_xmlid, role_code in CAPABILITY_MENUS.items():
            self.assertNotIn(
                menu_xmlid, baseline, "%s must be hidden from a baseline keeper" % menu_xmlid
            )
            cap_visible = self._visible_xmlids(self.role(role_code))
            self.assertIn(
                menu_xmlid, cap_visible, "%s must be visible to %s" % (menu_xmlid, role_code)
            )

    def test_manager_sees_configuration_and_approvals(self):
        visible = self._visible_xmlids(self.role("MGR"))
        for x in (
            "wms_location.menu_wms_config",
            "wms_barcode.menu_wms_issue_approval",
            "wms_reports.menu_wms_dashboard",
            "wms_location.menu_wms_cycle_count",
        ):
            self.assertIn(x, visible, "manager must see %s" % x)

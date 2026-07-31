"""Shared role factory + fixtures for the UI / multi-user certification.

This is NOT a test (no Test* class, no @tagged) so the runner does not discover
it. Cert test classes inherit ``CertRolesMixin`` to build the same set of role
users and seed fixtures ONCE in setUpClass.

Why setUpClass (runtime), never XML data: ``wms_location`` runs
``_wms_backfill_capabilities`` on every ``-u`` upgrade, granting the four
daily-work caps to every ``group_wms_user`` member. If the baseline keeper were
created at data-load time the backfill would silently hand it all four caps and
the "keeper can't see Scan/Damage/Audit" assertions would pass for the wrong
reason. setUpClass runs AFTER install/upgrade, so the baseline keeper stays
capability-free.
"""

# Role code -> (login, [group xmlids]). A capability sub-group already implies
# group_wms_user, so assigning only the cap yields "baseline + that cap".
_ROLE_GROUPS = {
    "MGR": ("cert_mgr", ["wms_location.group_wms_manager"]),
    "KEEPER_BASE": ("cert_keeper", ["wms_location.group_wms_user"]),
    "KEEPER_RECV": ("cert_recv", ["wms_location.group_wms_can_scan_receive"]),
    "KEEPER_ISSUE": ("cert_issue", ["wms_location.group_wms_can_scan_issue"]),
    "KEEPER_DMG": ("cert_dmg", ["wms_location.group_wms_can_file_damage"]),
    "KEEPER_AUDIT": ("cert_audit", ["wms_location.group_wms_can_submit_audit"]),
    "KEEPER_CAT": ("cert_cat", ["wms_location.group_wms_can_manage_catalog"]),
    "KEEPER_BACKUP": ("cert_backup", ["wms_reports.group_wms_backup_now"]),
    "BUYER": ("cert_buyer", ["wms_ai_forecast.group_buyer"]),
    "REPAIR": ("cert_repair", ["wms_repair_damage.group_repair_tech"]),
    "PLAIN": ("cert_plain", ["base.group_user"]),
    "PORTAL": ("cert_portal", ["base.group_portal"]),
}

# Menus a BASELINE keeper (group_wms_user, no caps) must NOT see. The capability
# menus are asserted separately (absent without the cap, present with it).
FORBIDDEN_FOR_BASELINE = [
    "wms_location.menu_wms_config",
    "wms_location.menu_wms_cycle_count",
    "wms_barcode.menu_wms_issue_approval",
    "wms_repair_damage.menu_wms_repair",
    "wms_barcode.menu_wms_product_onboard",
    "wms_reports.menu_wms_dashboard",
    "wms_reports.menu_wms_stock_value",
    "wms_reports.menu_wms_consumption_value",
]

# Capability menu xmlid -> the role code that should see it (and baseline must not).
CAPABILITY_MENUS = {
    "wms_barcode.menu_wms_scan_receipt": "KEEPER_RECV",
    "wms_barcode.menu_wms_scan_return": "KEEPER_RECV",
    "wms_barcode.menu_wms_scan_issue": "KEEPER_ISSUE",
    "wms_repair_damage.menu_wms_damage": "KEEPER_DMG",
    "wms_reports.menu_wms_audit": "KEEPER_AUDIT",
    "wms_barcode.menu_wms_barcode_alias": "KEEPER_CAT",
    "wms_reports.menu_wms_gdrive_backup_now": "KEEPER_BACKUP",
}


class CertRolesMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(
            no_reset_password=True, tracking_disable=True, mail_create_nosubscribe=True
        )
        cls.role_users = {}
        for code, (login, xmlids) in _ROLE_GROUPS.items():
            cls.role_users[code] = Users.create(
                {
                    "name": login,
                    "login": login,
                    "password": login + "_pw",
                    "group_ids": [(6, 0, [cls.env.ref(x).id for x in xmlids])],
                }
            )
        cls.ALL_ROLES = list(cls.role_users)

        # ---- shared fixtures -------------------------------------------------
        # A configured company report layout, so report_action returns the
        # report itself. Without it, an admin printing for the first time gets
        # Odoo's one-time "configure document layout" wizard (act_window) — a
        # standard Odoo quirk the operator clears at go-live by setting the
        # company letterhead.
        layout = cls.env.ref("web.external_layout_standard", raise_if_not_found=False)
        if layout and not cls.env.company.external_report_layout_id:
            cls.env.company.external_report_layout_id = layout.id

        cls.wh = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock = cls.wh.lot_stock_id

        # Product WITH a barcode so the thermal label PDF exercises the real
        # Code128 path (not the empty-barcode short-circuit).
        cls.cert_product = cls.env["product.product"].create(
            {
                "name": "CERT Widget",
                "type": "consu",
                "is_storable": True,
                "barcode": "CERTWIDGET01",
                # No explicit default_code: a SKU must match the Kind's prefix
                # (a real constraint), so let the module auto-assign it.
                "wms_product_kind": "consumable",
                "standard_price": 12.0,
            }
        )
        cls.env["stock.quant"]._update_available_quantity(cls.cert_product, cls.stock, 25.0)

        # A floor location WITH a barcode for the location-label PDF.
        cls.cert_location = cls.env["stock.location"].create(
            {
                "name": "CERT Floor",
                "usage": "internal",
                "location_id": cls.wh.lot_stock_id.id,
                "wms_location_type": "floor",
                "barcode": "CERTLOC01",
            }
        )

        # A forecast row with reorder_qty>0 so the Reorder Summary SQL view
        # returns at least one row when opened.
        cls.env["wms.forecast"].create({"product_id": cls.cert_product.id, "reorder_qty": 7.0})

        # A minimal real rack (1x1x1) so the /wms/rack/<id>/grid route can be
        # certified per role (the route 404s on a non-rack id).
        rack_wiz = cls.env["wms.rack.generator"].create(
            {
                "warehouse_id": cls.wh.id,
                "rack_code": "CERTRACK",
                "shelf_count": 1,
                "column_count": 1,
                "default_slot_count": 1,
            }
        )
        rack_wiz.action_generate()
        cls.cert_rack = cls.env["stock.location"].search(
            [("wms_location_type", "=", "rack"), ("wms_rack_code", "=", "CERTRACK")], limit=1
        )
        cls.env.flush_all()

    @classmethod
    def role(cls, code):
        return cls.role_users[code]

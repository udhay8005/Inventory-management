"""Uninstall non-WMS Odoo apps.

Strategy: for each candidate, compute the transitive set of dependents
upfront. If any dependent is in our KEEP_SAFE set, the uninstall would
cascade through WMS — skip that candidate. This avoids the
button_immediate_uninstall() being unrollbackable once started.
"""

UNWANTED = [
    "google_gmail",
    "microsoft_outlook",
    "snailmail_account",
    "snailmail",
    "stock_sms",
    "sms",
    "partner_autocomplete",
    "iap_mail",
    "iap",
    "spreadsheet_dashboard_stock_account",
    "spreadsheet_dashboard_account",
    "spreadsheet_dashboard",
    "spreadsheet_account",
    "spreadsheet",
    "onboarding",
    "digest",
    "web_unsplash",
]

KEEP_SAFE = {
    "stock",
    "purchase",
    "account",
    "portal",
    "barcodes",
    "barcodes_gs1_nomenclature",
    "product",
    "mail",
    "base",
    "web",
    "purchase_stock",
    "stock_account",
    "wms_location",
    "wms_fifo",
    "wms_barcode",
    "wms_repair_damage",
    "wms_ai_forecast",
    "wms_reports",
}

Module = env["ir.module.module"]
Dep = env["ir.module.module.dependency"]


def transitive_dependents(module_name, seen=None):
    """Set of installed module names that (transitively) depend on
    `module_name`."""
    if seen is None:
        seen = set()
    if module_name in seen:
        return set()
    seen.add(module_name)
    # Direct dependents: modules that declare module_name in their `depends`
    deps = Dep.search([("name", "=", module_name)])
    direct = {d.module_id.name for d in deps if d.module_id.state == "installed"}
    result = set(direct)
    for d in direct:
        result |= transitive_dependents(d, seen)
    return result


removed = []
skipped = []

for name in UNWANTED:
    mod = Module.search([("name", "=", name)], limit=1)
    if not mod or mod.state != "installed":
        skipped.append((name, f"state={mod.state if mod else 'missing'}"))
        continue

    dependents = transitive_dependents(name)
    if dependents & KEEP_SAFE:
        clash = sorted(dependents & KEEP_SAFE)[:5]
        skipped.append((name, f"would cascade through {clash}"))
        continue

    try:
        mod.button_immediate_uninstall()
        env.cr.commit()
        removed.append(name)
    except Exception as exc:
        skipped.append((name, str(exc).splitlines()[0][:80]))
        env.cr.rollback()

print("=== Removed ===")
for n in removed:
    print(" -", n)
print("=== Skipped ===")
for n, why in skipped:
    print(f" - {n}  ({why})")
print(f"Total: {len(removed)} removed, {len(skipped)} skipped.")

env.cr.execute("SELECT COUNT(*) FROM ir_module_module WHERE state='installed';")
print("Installed module count:", env.cr.fetchone()[0])

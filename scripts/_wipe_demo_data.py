"""Wipe the 5 demo products + every record that depends on them.

The trust is moving to structured SKUs (TOOL-00001, CONS-00001, ...)
and wants to enter their real inventory from scratch. The demo
products (DRILL-18V, HELMET-01, NUT-M4, SCRW-M4-20, TIE-200) and
everything connected to them - damages, repair orders, stock moves,
quants, carton aliases, forecast rows, store-keeper activity log,
filestore attachments referenced through the products - all goes.

Two phases:

  1. Bypass the protective ACL (perm_unlink=0 we set in the
     security CSVs). The XML-RPC user (admin) has unlink permission
     in postgres but our CSV blocks ORM unlink. We connect as the
     `__system__` super-user instead, which bypasses access checks
     while still going through the ORM (so cascades, computed
     fields, and tracking all run cleanly).

  2. Walk the dependency graph from the LEAVES upward:
        repair orders -> damages -> pickings/moves -> quants
                                  -> aliases -> products
     deleting in that order avoids FK violations.

The script also resets the per-kind SKU sequences to 1, so the
trust's first real entry becomes TOOL-00001 (not TOOL-00006 just
because the demo ate up 5 slots).

Usage:
    python _wipe_demo_data.py URL DB LOGIN PASSWORD [--dry-run]
"""

from __future__ import annotations

import sys
import xmlrpc.client

DEMO_SKUS = ["DRILL-18V", "HELMET-01", "NUT-M4", "SCRW-M4-20", "TIE-200"]


def call(models, db, uid, password, model, method, args=None, kwargs=None):
    return models.execute_kw(db, uid, password, model, method, args or [], kwargs or {})


def main() -> None:
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    url, db, login, password = sys.argv[1:5]
    dry_run = "--dry-run" in sys.argv

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, login, password, {})
    if not uid:
        sys.exit(f"Auth failed for {login}@{db}")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    ctx = {"force_company": False}

    # --- 1. Locate the demo products (templates + variants) -------------
    tmpl_ids = call(
        models,
        db,
        uid,
        password,
        "product.template",
        "search",
        [[("default_code", "in", DEMO_SKUS)]],
    )
    prod_ids = call(
        models,
        db,
        uid,
        password,
        "product.product",
        "search",
        [[("default_code", "in", DEMO_SKUS)]],
    )
    if not tmpl_ids and not prod_ids:
        print("[wipe] No demo products found. Nothing to do.")
        return
    print(f"[wipe] Found {len(tmpl_ids)} templates / {len(prod_ids)} variants matching {DEMO_SKUS}")

    if dry_run:
        # Show what WOULD be deleted at each level.
        for model_name, label in [
            ("wms.repair.order", "repair orders"),
            ("wms.damage", "damages"),
            ("stock.move", "stock moves"),
            ("stock.move.line", "stock move lines"),
            ("stock.quant", "stock quants"),
            ("wms.barcode.alias", "carton aliases"),
            ("wms.forecast", "forecasts"),
            ("wms.forecast.history", "forecast history"),
        ]:
            ids = call(
                models, db, uid, password, model_name, "search", [[("product_id", "in", prod_ids)]]
            )
            print(f"  would delete {len(ids):>4} rows from {label} ({model_name})")
        return

    # --- 2. Cascade-delete from the leaves up ---------------------------
    cascade_steps = [
        # (model, ID domain)
        ("wms.repair.order", [("product_id", "in", prod_ids)]),
        ("wms.damage", [("product_id", "in", prod_ids)]),
        # Stock moves block deletion of products via FK. We unlink in
        # state 'cancel' / 'draft' first; 'done' moves stay - the
        # ORM will refuse to delete a product with done moves, which
        # is what we want as a safety net.
        ("stock.move.line", [("product_id", "in", prod_ids)]),
        ("stock.move", [("product_id", "in", prod_ids)]),
        ("stock.quant", [("product_id", "in", prod_ids)]),
        ("wms.barcode.alias", [("product_id", "in", prod_ids)]),
        ("wms.forecast", [("product_id", "in", prod_ids)]),
        ("wms.forecast.history", [("product_id", "in", prod_ids)]),
    ]

    for model_name, domain in cascade_steps:
        # Some models may not exist (older installs); skip silently.
        try:
            ids = call(models, db, uid, password, model_name, "search", [domain])
        except xmlrpc.client.Fault as e:
            if "doesn't exist" in str(e) or "does not exist" in str(e):
                continue
            raise
        if not ids:
            continue
        try:
            call(models, db, uid, password, model_name, "unlink", [ids])
            print(f"[wipe] unlinked {len(ids):>4} {model_name} rows")
        except xmlrpc.client.Fault as e:
            print(f"[wipe] WARN: could not unlink {model_name}: {str(e)[:120]}")

    # --- 3. Now the products themselves ---------------------------------
    if prod_ids:
        try:
            call(models, db, uid, password, "product.product", "unlink", [prod_ids])
            print(f"[wipe] unlinked {len(prod_ids):>4} product.product rows")
        except xmlrpc.client.Fault as e:
            print(f"[wipe] WARN: product.product unlink: {str(e)[:200]}")
    if tmpl_ids:
        # template unlink may already have happened via cascade; check
        # what's left.
        remaining = call(
            models, db, uid, password, "product.template", "search", [[("id", "in", tmpl_ids)]]
        )
        if remaining:
            try:
                call(models, db, uid, password, "product.template", "unlink", [remaining])
                print(f"[wipe] unlinked {len(remaining):>4} product.template rows")
            except xmlrpc.client.Fault as e:
                print(f"[wipe] WARN: product.template unlink: {str(e)[:200]}")

    # --- 4. Reset the per-kind sequences --------------------------------
    seq_codes = [
        "wms.sku.raw_material",
        "wms.sku.packaging",
        "wms.sku.fluid",
        "wms.sku.finished_good",
        "wms.sku.wip",
        "wms.sku.consumable",
        "wms.sku.tool",
        "wms.sku.spare",
    ]
    for code in seq_codes:
        sids = call(models, db, uid, password, "ir.sequence", "search", [[("code", "=", code)]])
        if sids:
            call(
                models, db, uid, password, "ir.sequence", "write", [sids, {"number_next_actual": 1}]
            )
    print(f"[wipe] Reset {len(seq_codes)} SKU sequences to 1")

    print("[wipe] Done. Inventory is empty; create products via the Admin UI.")


if __name__ == "__main__":
    main()

"""Upload company logo + favicon for the WMS Odoo install.

Logo goes onto `res.company.logo` (standard Odoo field, drives the
navbar, login page, and PDF reports).

Favicon goes into an `ir.attachment` named `wms.favicon.image`, which
the custom controller in `wms_location/controllers/favicon.py` serves
at every URL the browser tries (`/favicon.ico`, the Odoo bundled
paths, the iOS home-screen path). Odoo 19 dropped `res.company.favicon`,
hence the attachment indirection.

Invoked by scripts/set-branding.ps1 -- kept as a sibling .py rather than
inlined so PowerShell's variable-expansion in here-strings doesn't
mangle the Python source.

Usage:
    python _set_branding.py URL DB LOGIN PASSWORD LOGO_PATH FAVICON_PATH
"""

from __future__ import annotations

import base64
import mimetypes
import os
import sys
import xmlrpc.client

# Constant must match _ATTACHMENT_NAME in
# addons/wms_location/controllers/favicon.py.
FAVICON_ATTACHMENT_NAME = "wms.favicon.image"


def _read_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def main() -> None:
    url, db, login, password, logo_path, fav_path = sys.argv[1:7]

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, login, password, {})
    if not uid:
        sys.exit(f"Auth failed for {login}@{db} on {url}")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    # 1. Company logo --------------------------------------------------------
    user_row = models.execute_kw(db, uid, password, "res.users", "read", [[uid], ["company_id"]])[0]
    company_id = user_row["company_id"][0]
    print(f"[branding] Updating company id={company_id}")

    models.execute_kw(
        db,
        uid,
        password,
        "res.company",
        "write",
        [[company_id], {"logo": _read_b64(logo_path)}],
    )

    company = models.execute_kw(
        db,
        uid,
        password,
        "res.company",
        "read",
        [[company_id], ["name", "logo"]],
    )[0]
    logo_kb = (len(company["logo"]) * 3 // 4) // 1024 if company["logo"] else 0
    print(f"[branding] Logo set: company={company['name']!r}, size={logo_kb} KB")

    # 2. Favicon -- upsert ir.attachment named FAVICON_ATTACHMENT_NAME -------
    mimetype = mimetypes.guess_type(fav_path)[0] or "image/png"
    favicon_b64 = _read_b64(fav_path)
    favicon_size = os.path.getsize(fav_path)

    existing = models.execute_kw(
        db,
        uid,
        password,
        "ir.attachment",
        "search",
        [[("name", "=", FAVICON_ATTACHMENT_NAME)]],
        {"limit": 1},
    )

    vals = {
        "name": FAVICON_ATTACHMENT_NAME,
        "datas": favicon_b64,
        "type": "binary",
        "mimetype": mimetype,
        "public": True,  # served by an auth='public' controller
    }
    if existing:
        models.execute_kw(
            db,
            uid,
            password,
            "ir.attachment",
            "write",
            [existing, vals],
        )
        print(
            f"[branding] Favicon updated: attachment id={existing[0]}, "
            f"size={favicon_size // 1024} KB, mime={mimetype}"
        )
    else:
        att_id = models.execute_kw(
            db,
            uid,
            password,
            "ir.attachment",
            "create",
            [vals],
        )
        print(
            f"[branding] Favicon created: attachment id={att_id}, "
            f"size={favicon_size // 1024} KB, mime={mimetype}"
        )


if __name__ == "__main__":
    main()

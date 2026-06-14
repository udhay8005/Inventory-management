# 08 — Security & access control

## Role model (two tiers: base role + capability sub-groups)

The trust runs a **two-tier** model: every user picks ONE base role, and the
Admin grants ONE OR MORE capability sub-groups on top. A bare Store Keeper
with no sub-groups can VIEW reports but cannot scan anything — this matches
how new hires are onboarded (shadow first, scan later).

```
Base roles                            Optional capability sub-groups
─────────────────────────────         ──────────────────────────────────
WMS / Store Keeper                 +  group_wms_can_scan_receive
WMS / Manager (= base + all)          group_wms_can_scan_issue
WMS / Repair Tech (= base + repair)   group_wms_can_file_damage
                                      group_wms_can_submit_audit
                                      group_wms_can_manage_catalog

(All capability sub-groups live in the `wms_location` namespace, e.g.
`wms_location.group_wms_can_scan_receive`.)
```

### Base roles

| Group | xml_id | Implies | Effect |
|---|---|---|---|
| WMS / Store Keeper | `wms_location.group_wms_user` | `stock.group_stock_user` | Read-only on reports + menus, until granted a capability sub-group. |
| WMS / Manager | `wms_location.group_wms_manager` | `stock.group_stock_manager`, `wms_location.group_wms_user`, ALL capability sub-groups | Everything — including racks, slot creation, label config, roster maintenance, /wms/dashboard, value reports, raw Inventory app access. |
| WMS / Repair Tech | `wms_repair_damage.group_repair_tech` | `wms_location.group_wms_user` | Adds write access on `wms.repair.order` for Start Repair / Mark Done / Scrap. |

### Capability sub-groups (granted PER USER by the Admin)

| Group | xml_id | Adds | Why it's separate |
|---|---|---|---|
| Can Scan Receipt / Return | `wms_location.group_wms_can_scan_receive` | Scan Receipt wizard + Scan Return | Two-step new-hire onboarding — receipts first, issues later. |
| Can Scan Issue | `wms_location.group_wms_can_scan_issue` | Scan Issue wizard (FIFO planner) | Issues have a daily cap + per-issue cap + audit triplet — only granted to keepers trusted with the budget. |
| Can File Damage | `wms_location.group_wms_can_file_damage` | wms.damage form + action_confirm | Damage events drive the urgent-buy recommendation and lock the source slot. Limited per the trust's accountability policy. |
| Can Submit Audit | `wms_location.group_wms_can_submit_audit` | wms.audit start + submit (Admin still accepts) | Auditors walk slots and submit counts; the Admin alone applies the variance delta. |
| Can Manage Catalog | `wms_location.group_wms_can_manage_catalog` | wms.barcode.alias + carton-label / catalog maintenance | Aliases are barcode-to-product mappings; collisions silently route stock to the wrong product if mismanaged. All five sub-groups are defined in the `wms_location` addon (single source of truth), even though they gate features in `wms_barcode`, `wms_repair_damage`, and `wms_reports`. |

### Bare Store Keeper = read-only

A user with ONLY `wms_location.group_wms_user` and NO capability sub-groups
can open WMS menus and read reports but cannot scan, damage, or audit. This
is the **shadow** state for a new hire — they can watch the screen during
training and read the manuals without being able to write.

The `admin` user is auto-added to `WMS / Manager` on first install of
`wms_location` (which implies every capability sub-group).

## Why Store Keepers keep `stock.group_stock_user` but lose the Inventory menu

WMS wizards create `stock.picking` records programmatically — for that they
need `stock.group_stock_user` ACL. But if the storekeeper can also reach the
**raw Inventory app menu**, they can create pickings WITHOUT going through
Scan Receipt — bypassing the QC checkbox, the on-duty roster, and the audit
chatter the wizards enforce.

Fix: `addons/wms_location/security/wms_security.xml` overrides
`stock.menu_stock_root.group_ids` to require `stock.group_stock_manager`. Store
Keepers retain `stock.group_stock_user` (so the wizards work) but they can no
longer browse Inventory directly. WMS workflows become the only path to move
stock as a Store Keeper.

## Audit-trail invariant

Every action that moves stock records three audit fields:

| Field | Type | Meaning |
|---|---|---|
| `wms_taken_by` / `wms_reported_by` / `wms_delivered_by` | Char | The human who physically handled the goods |
| `wms_ordered_by` / `wms_authorized_by` | Char | Who approved the move |
| `wms_storekeeper_id` | M2O → `wms.storekeeper` | Who was on the desk (picked from the roster) |

Fields are mirrored from the wizard / damage event / repair order onto the
resulting `stock.picking` plus a chatter `message_post`. The damage form's
`action_confirm` and the repair order's `_check_audit_complete` refuse to
move past draft when any of the three is blank — so an audit-blank record
can be drafted as scratch space but never committed.

The Store Keeper roster (`wms.storekeeper`) is admin-maintained under
**WMS → Configuration → Store Keepers**. Each entry is one human name
(Lakshmi, Ramesh, Suresh, …). The on-duty Odoo login (one shared account
per shift) is recorded automatically as `env.user.display_name` in the
chatter message, so the audit trail records BOTH "which human" and "which
Odoo session".

## Record rules

`wms_repair_damage` shipped without record rules — the ACL CSV alone covers
the security model:

| Model | Store Keeper | Repair Tech | Manager |
|---|---|---|---|
| `wms.damage` | RWC | RWC | RWCD |
| `wms.repair.order` | R + C only | RWC | RWCD |
| `wms.storekeeper` | R only | R only | RWCD |
| `wms.barcode.alias` | R only | R only | RWCD |
| `stock.picking` | RWC (no D) via `stock.group_stock_user` | inherits | inherits |

R=read, W=write, C=create, D=unlink.

Store Keepers having `create` but not `write` on `wms.repair.order` is
deliberate: they can click *Create Repair Order* on their damage event
(which inserts a fresh draft) but they can't subsequently mutate it.
The state-transition buttons (Start Repair / Mark Done / Scrap / Cancel)
are hidden from them via `groups=` on the view header.

## Audit messages

Every `mail.thread`-enabled model writes a `mail.message` on every state
change. These are immutable for non-Manager users. Each state transition
in `wms.damage` and `wms.repair.order` posts an explicit chatter audit
message via `_post_state_audit()`:

> **Repair started.** Item moved from Damage to Repair-Out and is now in
> the technician's hands.
>
> Reported by **Vimal (worker)**; authorised by **Krishna (cow-care lead)**;
> Store Keeper on duty: **Lakshmi**; logged in as: **Administrator**.

## Notifications

When a damage event resolves to `recommended_action = 'urgent_buy'`
(non-returnable product + 0 spare on hand), `wms.damage._notify_managers_urgent_buy()`
fans out a Discuss notification to every member of `WMS / Manager` via
`user.partner_id.message_post()`.

## Secrets

- All passwords in `.env`, never in checked-in config (`config/*.conf`) or in git.
- `admin_passwd` is the master-key for the DB manager; rotate after first install.
- Use Odoo's API keys feature for the optional AI worker rather than the user password if exposing across networks.

## Enumerated security controls (what ships live)

The following controls are shipped and verified in the live build — they are
not aspirational. Each maps to a concrete file or runtime artefact.

1. **Database manager UI hard-disabled.** `config/odoo.native.conf` ships with
   `list_db = False` **and** `db_listing = False`, plus a `/web/database/*`
   lockdown redirect in `wms_reports`. The DB selector is not reachable via
   URL guessing.
2. **Two-tier role model + five capability sub-groups.** Base roles —
   WMS / Store Keeper (`wms_location.group_wms_user`), WMS / Manager
   (`wms_location.group_wms_manager`), WMS / Repair Tech
   (`wms_repair_damage.group_repair_tech`), plus optional WMS / Buyer
   (`wms_location.group_buyer`). Five capability sub-groups, **all** in the
   `wms_location` namespace: `group_wms_can_scan_receive`,
   `group_wms_can_scan_issue`, `group_wms_can_file_damage`,
   `group_wms_can_submit_audit`, `group_wms_can_manage_catalog`.
3. **`/wms/health` is token-gated.** The route is `auth='public'` but
   compares the supplied token against the `ir.config_parameter`
   `wms_reports.health_token` via `odoo.tools.consteq` (constant-time).
   `install-native.ps1` auto-generates a 32-hex token at install time.
   Accepted as `?token=<v>` query string **or** `X-Health-Token` header.
   Missing/wrong → HTTP 401 `{"status":"unauthorized"}`; OK → 200 with the
   diagnostic JSON body; degraded → 503 with the same body shape;
   internal exception → 503 `{"status":"CRITICAL","detail":"health check failed"}`.
4. **Backup envelope cipher.** `scripts\backup-encrypted.ps1` invokes
   `GPG --symmetric --cipher-algo AES256`, passing the passphrase via a
   short-lived `--passphrase-file` invoked through `cmd /c` (the `cmd /c`
   hop avoids PowerShell 5.1's `NativeCommandError` on gpg-agent stderr).
5. **Integrity gate.** Each backup writes a SHA-256 checksum next to the
   `.gpg` envelope, and the restore drill runs `pg_restore --list` requiring
   **≥100 TOC entries** before the dump is considered good.
6. **Off-site copy is failure-safe.** `BACKUP_OFFSITE_DIR` is read **only**
   from `.env`. Blank → off-site disabled (local backup still succeeds).
   Set → the destination directory is created if missing, the `.gpg` is
   copied, SHA-256 is **re-verified at the destination**, and retention is
   mirrored (`-Retain`, default 14). Any off-site failure is swallowed so it
   never fails the local backup.
7. **Scheduled tasks run as SYSTEM.** All three of `WMS Daily Backup`
   (4:30 PM daily), `WMS Weekly Restore Drill` (3:00 AM Sunday), and
   `WMS Manual Backup` (trigger-less; run on demand by the Backup Now
   wizard via `schtasks /Run`) are registered with principal
   `NT AUTHORITY\SYSTEM`, `LogonType=ServiceAccount`, `RunLevel=Highest`,
   `-StartWhenAvailable`, `ExecutionTimeLimit=2h`,
   `MultipleInstances=IgnoreNew`. Because they run as SYSTEM, any
   `BACKUP_OFFSITE_DIR` path must be reachable by SYSTEM (UNC paths need a
   pre-cached SYSTEM credential).
8. **Placeholder-password rejection.** `install-native.ps1` rejects obvious
   placeholder strings (`changeme*`, `admin`, and similar) before bringing
   the service up — first-install operators cannot ship the trust with the
   sample password still in `.env`.
9. **Google Drive uploads use the minimal `drive.file` scope.** The optional
   Drive integration requests exactly one OAuth scope, `drive.file` — the
   app can see and touch only files it created (the `Inventory_Backups`
   tree), never the rest of the Drive or the Google account. There is no
   drive-wide read scope anywhere in the pipeline, and the uploaded
   artefacts remain GPG AES256 ciphertext (the passphrase never leaves the
   box).
10. **The Drive refresh token is DPAPI machine-scope.** The OAuth refresh
    token lives at `config\gdrive-token.json.dpapi`, encrypted with DPAPI
    LocalMachine scope so the `NT AUTHORITY\SYSTEM` scheduled tasks can read
    it while an exfiltrated copy is useless off-box. The file is gitignored;
    rotation = re-run `scripts\setup-gdrive-auth.ps1` (one browser consent).
11. **Drive uploads are checksum-verified without re-download.** After every
    upload, the Drive-side `sha256Checksum` must equal the SHA-256 already
    computed locally for the artefact; a mismatch deletes the remote file
    and counts the upload as failed. The Drive stage is failure-safe — any
    Drive error is logged and audited but never fails the local backup.
12. **Drive restore into production is double-gated.** `gdrive-restore.ps1`
    refuses to restore into the live `wms` database unless BOTH `-Force` AND
    the literal `-ConfirmTarget wms` are passed — otherwise it exits 5
    (PROD_GUARD) before any side effect. Storekeepers have no restore
    surface at all: the restore browser, catalog, and settings are
    manager-only menus and ACLs.

## Hardening checklist

- [ ] Change all defaults in `.env`.
- [ ] Set `proxy_mode=True` only when behind a real TLS terminator.
- [x] Disable the database manager in prod: `list_db = False` AND `db_listing = False` in `config/odoo.native.conf` (shipped + verified live).
- [ ] Restrict `pg_hba` so only the local Odoo service (127.0.0.1, system user) can reach PostgreSQL on port 1088.
      Note: port **1088** (not the PG default 5432) is used to avoid clashing with any pre-existing PostgreSQL instance already on the box — `config/odoo.native.conf` ships with `db_port = 1088` to match. `db_host=localhost` in `odoo.native.conf` only controls Odoo's **client** connection to PostgreSQL — Odoo's HTTP server still binds `0.0.0.0:8069` unless `http_interface` is set in the conf. Both the `pg_hba` lockdown and an explicit `http_interface = 127.0.0.1` (when fronted by IIS/nginx) are open hardening tasks.
- [x] Token-gate `/wms/health`: install-native auto-generates a 32-char hex `wms_reports.health_token` parameter (verified live: anonymous probes return `{"status":"unauthorized"}` with HTTP 401).
- [ ] Branch protection on `main`: require PR + green CI before merge.
- [ ] Run the following monthly for Odoo CE security patches (PowerShell 5.1-safe chaining — `if ($?)` runs the next step only if the previous one succeeded): `cd .odoo; if ($?) { git pull origin 19.0 }; if ($?) { cd .. }; if ($?) { .venv\Scripts\pip install -r .odoo\requirements.txt --upgrade }`; then restart with `scripts\start-native.ps1`.
- [ ] Schedule `pg_dump` backups + restore drill quarterly.

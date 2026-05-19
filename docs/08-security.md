# 08 — Security & access control

## Role model (two roles + optional sub-roles)

```
WMS / Store Keeper   ← every-day operator (scan, file damage, file repair-create)
WMS / Manager        ← Admin (everything)
WMS / Repair Tech    ← optional sub-role on top of Store Keeper, granted only when needed
```

| Group | xml_id | Implies | Capabilities |
|---|---|---|---|
| WMS / Store Keeper | `wms_location.group_wms_user` | `stock.group_stock_user` | Scan Receipt / Return / Issue, file Damage, click Create-Repair-Order, view-only on resulting Repair Orders, all reports |
| WMS / Manager | `wms_location.group_wms_manager` | `stock.group_stock_manager`, `wms_location.group_wms_user` | Everything — including racks, slot creation, label config, roster maintenance, raw Inventory app access |
| WMS / Repair Tech | `wms_repair_damage.group_repair_tech` | `wms_location.group_wms_user` | Adds write access on `wms.repair.order` for Start Repair / Mark Done / Scrap |

The `admin` user is auto-added to `WMS / Manager` on first install of
`wms_location`.

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

- All passwords in `.env`, never in compose or in git.
- `admin_passwd` is the master-key for the DB manager; rotate after first install.
- Use Odoo's API keys feature for the optional AI worker rather than the user password if exposing across networks.

## Hardening checklist

- [ ] Change all defaults in `.env`.
- [ ] Set `proxy_mode=True` only when behind a real TLS terminator.
- [ ] Disable the database manager in prod: `list_db = False` in `config/odoo.conf`.
- [ ] Restrict `pg_hba` to the Docker subnet.
- [ ] Branch protection on `main`: require PR + green CI before merge.
- [ ] Run `docker compose pull` and rebuild monthly for Odoo CE security patches.
- [ ] Schedule `pg_dump` backups + restore drill quarterly.

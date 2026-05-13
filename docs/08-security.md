# 08 — Security & access control

## Odoo groups defined

| Group | xml_id | Inherits | Capabilities |
|---|---|---|---|
| WMS / User | `wms_location.group_wms_user` | `stock.group_stock_user` | scan, receive, issue, view stock |
| WMS / Manager | `wms_location.group_wms_manager` | `stock.group_stock_manager`, `wms_user` | create racks, adjust, see all reports |
| WMS / Repair Tech | `wms_repair_damage.group_repair_tech` | `wms_user` | repair workflow only |
| WMS / Buyer | `wms_ai_forecast.group_buyer` | `wms_user`, `purchase.group_purchase_user` | see forecasts, push to PO |

## Record rules

- A *User* sees only quants in warehouses they're assigned to (via Odoo's
  built-in `stock.group_stock_multi_warehouses`).
- *Repair Tech* can only modify `wms.repair.order` they're assigned to.
- *Buyer* can only see/act on forecasts; cannot edit racks.

## Access control matrix (`ir.model.access.csv`)

Each module ships its own CSV. Snippet for `wms_location`:

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_stock_loc_user,wms.stock.location.user,stock.model_stock_location,group_wms_user,1,0,0,0
access_stock_loc_mgr,wms.stock.location.manager,stock.model_stock_location,group_wms_manager,1,1,1,1
```

## Audit trail

- Every transactional model inherits `mail.thread` → automatic chatter, message
  log, attachments.
- Every state change writes a `mail.message`. These are immutable for non-admin.
- `ir.logging` captures cron and exception trails.

## Secrets

- All passwords in `.env`, never in compose or in git.
- `admin_passwd` is master-key for db manager; rotate after first install.
- Use Odoo's "API keys" feature for the optional AI worker rather than the
  user password if exposing across networks.

## Hardening checklist

- [ ] Change all defaults in `.env`.
- [ ] `proxy_mode=True` only when behind a real TLS terminator.
- [ ] Disable the database manager in prod: `list_db = False` in odoo.conf.
- [ ] Restrict `pg_hba` to the Docker subnet.
- [ ] Run `docker compose pull` and rebuild monthly for Odoo CE security patches.
- [ ] Schedule pg_dump backups + restore drill quarterly.

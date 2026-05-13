# 07 — Deployment

## First-time bring-up

```bash
cp .env.example .env
# edit .env — change all default passwords

docker compose build
docker compose up -d            # db + odoo
docker compose --profile ai up -d   # add AI worker (optional)

# initialize a database via UI:
#   http://localhost:8069/web/database/manager
#   master pwd = ODOO_ADMIN_PASSWD from .env
#   db name    = ODOO_DB from .env
#   tick "Load demonstration data" if you want sample racks/products
```

After login: **Apps → Update Apps List → search "wms" → install in order**:

1. `wms_location`
2. `wms_fifo`
3. `wms_barcode`
4. `wms_repair_damage`
5. `wms_ai_forecast`
6. `wms_reports`

## Day-2 ops

```bash
# Logs
docker compose logs -f odoo

# Shell into Odoo container
docker compose exec odoo bash

# psql
docker compose exec db psql -U odoo -d wms

# Restart only Odoo (DB stays up)
docker compose restart odoo
```

## Backups

```bash
chmod +x scripts/backup.sh
./scripts/backup.sh
```

Schedule via host cron / Task Scheduler. Default retention: 14 days, both DB
dump and filestore tarball.

Restore:

```bash
# DB
docker compose exec -T db pg_restore -U odoo -C -d postgres < backups/wms_YYYYMMDD.dump

# Filestore
docker run --rm --volumes-from wms_odoo \
  -v "$(pwd)/backups":/backup alpine \
  tar xzf /backup/filestore_YYYYMMDD.tar.gz -C /var/lib/odoo
```

## HTTPS / production

Put nginx or Caddy in front:

```
upstream odoo  { server odoo:8069; }
upstream chat  { server odoo:8072; }
server {
  listen 443 ssl http2;
  location /websocket { proxy_pass http://chat;  proxy_http_version 1.1; ... }
  location /          { proxy_pass http://odoo; ... }
}
```

`proxy_mode=True` is already set in `config/odoo.conf`.

## Logging

- `docker logs wms_odoo` mirrors `/var/log/odoo/odoo.log`.
- Ship to Loki/ELK with the standard Docker logging driver if needed.

## Optional barcode printer

Any thermal printer the **host OS** can see. Container generates PDF via the
existing report engine; PDF download is sent to the printer through the user's
browser (no special driver inside container).

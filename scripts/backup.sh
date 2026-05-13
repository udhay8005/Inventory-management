#!/usr/bin/env bash
# Nightly backup script — run from host via cron or systemd timer:
#   0 2 * * *  /path/to/scripts/backup.sh
# Produces a compressed pg_dump + a tarball of the filestore.
set -euo pipefail

DB_NAME="${ODOO_DB:-wms}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[backup] dumping database $DB_NAME"
docker exec wms_db pg_dump -U "${DB_USER:-odoo}" -Fc "$DB_NAME" \
  > "$BACKUP_DIR/${DB_NAME}_${STAMP}.dump"

echo "[backup] archiving filestore"
docker run --rm \
  --volumes-from wms_odoo \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine \
  tar czf "/backup/filestore_${STAMP}.tar.gz" -C /var/lib/odoo .

echo "[backup] pruning anything older than ${RETAIN_DAYS}d"
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+${RETAIN_DAYS}" -delete

echo "[backup] done -> $BACKUP_DIR"

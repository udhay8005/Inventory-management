#!/usr/bin/env bash
# Nightly backup — writes a Postgres custom-format dump + a tarball of the
# Odoo filestore, then prunes archives older than RETAIN_DAYS.
#
# Usage:  ./scripts/backup.sh
# Schedule via host cron / systemd timer / Windows Task Scheduler.
#
# Why we don't use `pg_dump > file.dump` directly:
#   On Windows PowerShell, the `>` redirect treats the binary stream as
#   text and corrupts it (UTF-16 / CRLF mangling). Generating the dump
#   inside the db container then `docker cp`-ing it out is binary-safe
#   on every OS.
set -euo pipefail

DB_NAME="${ODOO_DB:-wms}"
DB_USER="${DB_USER:-odoo}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

DUMP_NAME="${DB_NAME}_${STAMP}.dump"
TAR_NAME="filestore_${STAMP}.tar.gz"

echo "[backup] dumping database $DB_NAME"
docker compose exec -T db \
    pg_dump -U "$DB_USER" -Fc -f "/tmp/${DUMP_NAME}" "$DB_NAME"
docker cp "wms_db:/tmp/${DUMP_NAME}" "${BACKUP_DIR}/${DUMP_NAME}"
docker compose exec -T db rm "/tmp/${DUMP_NAME}"

echo "[backup] archiving filestore"
docker run --rm \
    --volumes-from wms_odoo \
    -v "$(pwd)/${BACKUP_DIR}:/backup" \
    alpine \
    tar czf "/backup/${TAR_NAME}" -C /var/lib/odoo .

echo "[backup] pruning anything older than ${RETAIN_DAYS}d"
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+${RETAIN_DAYS}" -delete

echo "[backup] done"
ls -lh "${BACKUP_DIR}/${DUMP_NAME}" "${BACKUP_DIR}/${TAR_NAME}"

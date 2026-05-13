#!/usr/bin/env bash
# Runs once on first PostgreSQL boot (docker-entrypoint-initdb.d).
# Grants CREATEDB so Odoo can create/restore databases from the UI.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
  ALTER USER "$POSTGRES_USER" CREATEDB;
EOSQL

#!/usr/bin/env bash
# One-time provisioning of the genaiforge role + database on a natively installed
# Postgres. Compose no longer runs a Postgres service, so every dev machine
# needs this once. Idempotent apart from the optional restore.
#
# Usage: scripts/setup-host-db.sh [dump.sql]
#   dump.sql  optional pg_dump file to load (e.g. exported from an old
#             compose Postgres volume). Omit it and run alembic instead.
set -euo pipefail

DUMP="${1:-}"
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5432}"
SUPERUSER="${PGSUPERUSER:-postgres}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  read -rsp "Password for Postgres superuser '${SUPERUSER}' on ${HOST}:${PORT}: " PGPASSWORD
  echo
  export PGPASSWORD
fi

su() { psql -h "$HOST" -p "$PORT" -U "$SUPERUSER" -d postgres -v ON_ERROR_STOP=1 "$@"; }

echo "==> Role 'genaiforge'"
su -c "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genaiforge') THEN
    CREATE ROLE genaiforge LOGIN PASSWORD 'genaiforge';
  ELSE
    ALTER ROLE genaiforge LOGIN PASSWORD 'genaiforge';
  END IF;
END \$\$;"

echo "==> Database 'genaiforge'"
if su -tAc "SELECT 1 FROM pg_database WHERE datname = 'genaiforge'" | grep -q 1; then
  echo "    already exists"
else
  su -c "CREATE DATABASE genaiforge OWNER genaiforge"
fi

if [[ -n "$DUMP" ]]; then
  echo "==> Restoring $DUMP"
  PGPASSWORD=genaiforge psql -h "$HOST" -p "$PORT" -U genaiforge -d genaiforge \
    -v ON_ERROR_STOP=1 -f "$DUMP" >/dev/null
else
  echo "==> No dump given; run 'alembic upgrade head' (the API also does this on boot)"
fi

echo "==> Verifying as 'genaiforge'"
PGPASSWORD=genaiforge psql -h "$HOST" -p "$PORT" -U genaiforge -d genaiforge -Atc \
  "select 'OK, tables=' || count(*) from information_schema.tables where table_schema='public'"

echo "==> Done. Now: docker compose up"

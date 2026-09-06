#!/usr/bin/env bash
# Start local dependencies and apply migrations.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Starting Postgres..."
docker compose up -d postgres

echo "Waiting for Postgres..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U genaiforge >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

cd backend
export PYTHONPATH=.
VENV="${ROOT}/venv/bin"
if [[ ! -x "$VENV/alembic" ]]; then
  VENV="${ROOT}/backend/.venv/bin"
fi

echo "Running migrations..."
"$VENV/alembic" upgrade head
"$VENV/python" -m app.scripts.seed
echo "Done. Postgres is on localhost:5433 — run uvicorn from backend/ next."

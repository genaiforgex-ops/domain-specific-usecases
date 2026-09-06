#!/usr/bin/env bash
# Stop anything on the app ports, then run the whole stack (backend + frontend).
# Backend migrates (alembic upgrade head) before serving. Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5180

# Use the local Postgres (matches docker-compose's db service and the config.py
# default). Exported here so it overrides backend/.env's remote UAT DATABASE_URL
# for both `alembic` and `uvicorn` (real env vars win over the .env file).
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/orchestration"

# ── Free a TCP port by killing whatever is listening on it ───────────────────
kill_port() {
  local port="$1" pids
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "${port}/tcp" 2>/dev/null || true)"
  fi
  if [ -n "${pids:-}" ]; then
    echo "Stopping process(es) on port ${port}: ${pids}"
    kill ${pids} 2>/dev/null || true
    sleep 1
    kill -9 ${pids} 2>/dev/null || true
  fi
}

# ── Tear down both children on exit (Ctrl+C, error, or normal end) ───────────
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Shutting down..."
  [ -n "${BACK_PID:-}" ] && kill "${BACK_PID}" 2>/dev/null || true
  [ -n "${FRONT_PID:-}" ] && kill "${FRONT_PID}" 2>/dev/null || true
  kill_port "${BACKEND_PORT}"
  kill_port "${FRONTEND_PORT}"
}
trap cleanup INT TERM EXIT

echo "==> Freeing ports ${BACKEND_PORT} and ${FRONTEND_PORT}"
kill_port "${BACKEND_PORT}"
kill_port "${FRONTEND_PORT}"

# ── Backend: migrate, then serve ─────────────────────────────────────────────
echo "==> Starting backend on :${BACKEND_PORT}"
cd "${ROOT}/backend"

# Create the virtualenv and install deps on first run (or if it's missing).
if [ ! -f .venv/bin/activate ]; then
  echo "==> Creating backend virtualenv (.venv)"
  # Prefer an interpreter the pinned deps have wheels for (Dockerfile targets
  # 3.12). Newer runtimes (e.g. 3.14) lack wheels for psycopg-binary et al.
  PYTHON=""
  for cand in python3.12 python3.13 python3.11 python3 python; do
    if command -v "${cand}" >/dev/null 2>&1; then PYTHON="$(command -v "${cand}")"; break; fi
  done
  if [ -z "${PYTHON}" ]; then
    echo "ERROR: no suitable python found on PATH (need 3.11–3.13)" >&2
    exit 1
  fi
  echo "    using ${PYTHON} ($("${PYTHON}" --version 2>&1))"
  "${PYTHON}" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

alembic upgrade head
uvicorn app.main:app --reload --port "${BACKEND_PORT}" &
BACK_PID=$!
deactivate

# ── Frontend: install deps if missing, then dev server ───────────────────────
echo "==> Starting frontend on :${FRONTEND_PORT}"
cd "${ROOT}/frontend"
[ -d node_modules ] || npm install
npm run dev &
FRONT_PID=$!

echo
echo "Backend:  http://localhost:${BACKEND_PORT}  (docs at /docs)"
echo "Frontend: http://localhost:${FRONTEND_PORT}"
echo "Press Ctrl+C to stop both."

# Exit (and trigger cleanup) as soon as either process dies. `wait -n` needs
# bash 4.3+, but macOS ships bash 3.2 — so poll both PIDs portably instead.
while kill -0 "${BACK_PID}" 2>/dev/null && kill -0 "${FRONT_PID}" 2>/dev/null; do
  sleep 1
done

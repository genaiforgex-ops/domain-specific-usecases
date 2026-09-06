#!/usr/bin/env bash
# Recreate the backend virtualenv with Python 3.12 (project standard).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY312=""
for candidate in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY312="$candidate"
    break
  fi
done

if [[ -z "$PY312" ]]; then
  echo "Python 3.12 not found."
  echo ""
  echo "Install it first (macOS):"
  echo "  brew install python@3.12"
  echo "  # then add to PATH, e.g.:"
  echo "  export PATH=\"/opt/homebrew/opt/python@3.12/bin:\$PATH\""
  echo ""
  echo "Or download from https://www.python.org/downloads/release/python-3120/"
  exit 1
fi

echo "Using: $($PY312 --version) at $(command -v "$PY312")"

if [[ -d .venv ]]; then
  echo "Removing existing .venv …"
  rm -rf .venv
fi

"$PY312" -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Done. Activate with:"
echo "  source $ROOT/.venv/bin/activate"

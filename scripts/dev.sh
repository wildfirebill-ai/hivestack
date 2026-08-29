#!/usr/bin/env bash
# hivestack launcher (Unix) — API on :8110, Vite dev server on :5173.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "venv not found. Run:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

echo "[hivestack] API    -> http://127.0.0.1:8110  (health: /health)"
echo "[hivestack] Web    -> http://127.0.0.1:5173  (login: admin / HIVESTACK_ADMIN_PASSWORD, default hivestack)"

(
  ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8110 --app-dir backend
) &
API_PID=$!

(
  cd web && npm run dev
) &
WEB_PID=$!

trap 'kill "$API_PID" "$WEB_PID" 2>/dev/null || true' EXIT
wait
#!/usr/bin/env bash
# hivestack — run the offline end-to-end suite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/tests/e2e_offline.py" "$@"
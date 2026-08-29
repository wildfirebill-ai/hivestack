#!/usr/bin/env bash
# hivestack container entrypoint — prepare volumes, print GPU banner, run API.
set -euo pipefail

mkdir -p /config /data /models

# First boot: seed a default config the user can edit.
if [ ! -f /config/config.yaml ]; then
  cp /app/backend/app/default_config.yaml /config/config.yaml
  echo "[hivestack] wrote default /config/config.yaml"
fi

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader >/dev/null 2>&1; then
  echo "[hivestack] GPU present:"
  nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv
else
  echo "[hivestack] no usable nvidia-smi — running CPU-only (fine for Stage 1; attach GPU for Stage 2+ inference)"
fi

# Background maintenance: periodic VACUUM + dated backups (see maintenance.sh).
if command -v /usr/local/bin/hivestack-maintenance >/dev/null 2>&1; then
  /usr/local/bin/hivestack-maintenance &
  echo "[hivestack] maintenance loop started"
fi

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${HIVESTACK_PORT:-8080}" \
  --app-dir /app/backend \
  "$@"
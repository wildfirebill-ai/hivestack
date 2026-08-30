#!/usr/bin/env bash
# hivestack container entrypoint — prepare volumes, print GPU banner, run API.
set -euo pipefail

mkdir -p /config /data /models

# First boot: seed a default config the user can edit.
if [ ! -f /config/config.yaml ]; then
  cp /app/backend/app/default_config.yaml /config/config.yaml
  echo "[hivestack] wrote default /config/config.yaml"
fi

echo "[hivestack] NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-<unset>} NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES:-<unset>}"
# GPU detection: prefer nvidia-smi, fall back to device/proc files (runtime may inject devices without nvidia-smi binary)
gpu_ok=0
if command -v nvidia-smi >/dev/null 2>&1; then
  if nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader >/dev/null 2>&1; then
    echo "[hivestack] GPU present (via nvidia-smi):"
    nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv || true
    gpu_ok=1
  else
    echo "[hivestack] nvidia-smi present but query failed (driver mismatch?)"
  fi
fi
if [ "$gpu_ok" -eq 0 ]; then
  if [ -c /dev/nvidiactl ] || [ -e /proc/driver/nvidia/version ] || ls /dev/nvidia[0-9]* >/dev/null 2>&1; then
    echo "[hivestack] GPU devices detected (no nvidia-smi binary, but driver devices present):"
    ls -l /dev/nvidia* /dev/nvidiactl 2>&1 | sed 's/^/[hivestack]  /' || true
    if [ -f /proc/driver/nvidia/version ]; then
      echo "[hivestack] $(cat /proc/driver/nvidia/version | head -1)"
    fi
    gpu_ok=1
  fi
fi
if [ "$gpu_ok" -eq 0 ]; then
  echo "[hivestack] no GPU devices found — running CPU-only (fine for Stage 1; set GPU UUID + recreate container for Stage 2+ inference)"
  echo "[hivestack] hint: verify Unraid NVIDIA Driver plugin enabled, container recreated after setting GPU UUID, and check 'docker inspect hivestack --format {{.HostConfig.Runtime}}' should be 'nvidia'"
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
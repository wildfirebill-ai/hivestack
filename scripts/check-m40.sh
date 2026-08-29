#!/usr/bin/env bash
# hivestack — GPU check (any host with nvidia-smi).
# Confirms a CC 5.x Maxwell (e.g. Tesla M40) is visible for Stage 2+ inference.
set -uo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "[hivestack] nvidia-smi not found — CPU-only node."
  exit 1
fi

nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version,compute_cap --format=csv
cc="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits | head -n1 | cut -d. -f1)"
cc="${cc:-0}"

if [ "$cc" -ge 7 ]; then
  echo "[hivestack] CC $cc — modern GPU; vLLM-class engines viable."
else
  echo "[hivestack] CC $cc — Maxwell/Pascal path: Ollama or llama.cpp (fp32/GGUF). vLLM not supported."
fi
#!/usr/bin/env bash
# hivestack — build the full image (Web UI + runtime).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker build -f docker/Dockerfile -t hivestack:0.1.0 .
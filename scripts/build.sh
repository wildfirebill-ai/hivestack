#!/usr/bin/env bash
# hivestack — build the full image (Web UI + runtime).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
docker build -f docker/Dockerfile -t "hivestack:${VERSION}" .
echo "[hivestack] built hivestack:${VERSION}  (aliased hivestack:latest)"
docker tag "hivestack:${VERSION}" hivestack:latest
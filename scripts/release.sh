#!/usr/bin/env bash
# hivestack — tagged release: build the image, push to GitHub Container Registry,
# and print the matching `git tag` to cut. Requires a GHCR token in GITHUB_TOKEN
# (or `docker login ghcr.io`) with `write:packages` on wildfirebill-ai/hivestack.
#
#   ./scripts/release.sh              # build + push :<version> and :latest
#   ./scripts/release.sh --no-push    # just build locally
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
REPO="ghcr.io/wildfirebill-ai/hivestack"
PUSH=1
if [[ "${1:-}" == "--no-push" ]]; then PUSH=0; fi

# 1) build the runtime image (Web UI baked in at build time)
docker build -f docker/Dockerfile -t "hivestack:${VERSION}" .
docker tag "hivestack:${VERSION}" hivestack:latest
echo "[hivestack] built hivestack:${VERSION}"

if [[ "$PUSH" == "1" ]]; then
  if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "[hivestack] GITHUB_TOKEN unset — authenticating from existing docker login."
  else
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u wildfirebill --password-stdin >/dev/null
  fi
  docker tag "hivestack:${VERSION}" "${REPO}:${VERSION}"
  docker tag "hivestack:${VERSION}" "${REPO}:latest"
  docker push "${REPO}:${VERSION}"
  docker push "${REPO}:latest"
  echo "[hivestack] pushed ${REPO}:${VERSION} and ${REPO}:latest"
fi

echo
echo "[hivestack] cut the release tag when ready:"
echo "    git tag -a v${VERSION} -m \"Release v${VERSION}\" && git push origin v${VERSION}"

# hivestack — build the full image
#   1) builds the Web UI, 2) bakes it into the Python runtime image.
$ErrorActionPreference = 'Stop'
docker build -f docker/Dockerfile -t hivestack:0.1.0 .
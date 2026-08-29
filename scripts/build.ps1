# hivestack — build the full image
#   1) builds the Web UI, 2) bakes it into the Python runtime image.
$ErrorActionPreference = 'Stop'
$version = (Get-Content (Join-Path $PSScriptRoot '..\VERSION')).Trim()
docker build -f docker\Dockerfile -t "hivestack:$version" .
docker tag "hivestack:$version" hivestack:latest
Write-Host "[hivestack] built hivestack:$version  (aliased hivestack:latest)"
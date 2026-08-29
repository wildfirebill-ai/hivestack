# hivestack — backup the platform.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'scripts\backup.py') @args
exit $LASTEXITCODE
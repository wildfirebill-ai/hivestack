# hivestack — run the offline end-to-end suite.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'tests\e2e_offline.py') @args
exit $LASTEXITCODE
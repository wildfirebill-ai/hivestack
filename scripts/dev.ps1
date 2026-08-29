# hivestack launcher (Windows / PowerShell)
# Starts the API on :8110 and the Vite dev server on :5173.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$api = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $api)) {
  Write-Error "venv not found. Run: python -m venv .venv; .\.venv\Scripts\python -m pip install -r backend\requirements.txt"
}
Start-Process -FilePath $api -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8110','--app-dir','backend') -WorkingDirectory $root -WindowStyle Hidden
Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev') -WorkingDirectory (Join-Path $root 'web') -WindowStyle Hidden

Write-Host ''
Write-Host 'hivestack dev:'
Write-Host '  API   http://127.0.0.1:8110  (health: /health)'
Write-Host '  Web   http://127.0.0.1:5173  (login: admin / HIVESTACK_ADMIN_PASSWORD, default hivestack)'
Write-Host 'Stop the two spawned processes to quit.'
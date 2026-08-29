# hivestack — GPU check (works on any host with nvidia-smi)
# Confirms the M40 (or any CC 5.x Maxwell) is visible for Stage 2+ inference.

$ErrorActionPreference = 'Stop'
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
  Write-Host '[hivestack] nvidia-smi not found — CPU-only node.' -ForegroundColor Yellow
  exit 1
}
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version,compute_cap --format=csv
$cc = (nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits | Select-Object -First 1).Trim().Split('.')[0]
if ([int]$cc -ge 7) {
  Write-Host "[hivestack] CC $cc — modern GPU; note vLLM-class engines are viable here too." -ForegroundColor Cyan
} else {
  Write-Host "[hivestack] CC $cc — Maxwell/Pascal path: Ollama or llama.cpp (fp32/GGUF). vLLM not supported." -ForegroundColor Yellow
}
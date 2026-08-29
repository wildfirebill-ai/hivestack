"""GPU detection via nvidia-smi. Informational in Stage 1; powers the dashboard
and later model-offload decisions."""

from __future__ import annotations

import shutil
import subprocess


def detect() -> dict:
    if shutil.which("nvidia-smi") is None:
        return {"present": False, "reason": "nvidia-smi not found (CPU-only fallback)"}
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover
        return {"present": False, "reason": str(exc)}
    if out.returncode != 0:
        return {"present": False, "reason": out.stderr.strip() or "nvidia-smi query failed"}

    gpus: list[dict] = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5:
            try:
                gpus.append(
                    {
                        "name": parts[0],
                        "memory_total_mib": int(parts[1]),
                        "memory_used_mib": int(parts[2]),
                        "driver_version": parts[3],
                        "compute_capability": parts[4],
                    }
                )
            except ValueError:
                continue

    cc = gpus[0].get("compute_capability", "0") if gpus else "0"
    try:
        major = int(cc.split(".")[0])
    except ValueError:
        major = 0
    return {
        "present": bool(gpus),
        "gpus": gpus,
        # informative only: decisions live in PLAN.md §5 / D2
        "vllm_supported": major >= 7,
        "ollama_supported": 0 < major <= 6,  # CC 5.0–6.x confirmed by ollama docs
    }
"""GPU detection via nvidia-smi. Informational in Stage 1; powers the dashboard
and later model-offload decisions."""

from __future__ import annotations

import shutil
import subprocess


def _fallback_from_proc() -> dict | None:
    """Try to infer GPU presence without nvidia-smi (device nodes / proc)."""
    import os
    import glob
    import re

    has_dev = bool(glob.glob("/dev/nvidia[0-9]*")) or os.path.exists("/dev/nvidiactl")
    has_proc = os.path.exists("/proc/driver/nvidia/version")
    visible = os.environ.get("NVIDIA_VISIBLE_DEVICES", "")
    driver_ver = "unknown"
    if has_proc:
        try:
            with open("/proc/driver/nvidia/version") as f:
                m = re.search(r"NVRM version: NVIDIA UNIX x86_64 Kernel Module\s+(\S+)", f.read())
                if m:
                    driver_ver = m.group(1)
        except Exception:
            pass
    if has_dev or has_proc:
        gpus: list[dict] = []
        # Try to enumerate via /proc if possible; else synthetic entry from env
        dev_count = len(glob.glob("/dev/nvidia[0-9]*"))
        if dev_count == 0 and has_proc:
            dev_count = 1
        for i in range(max(1, dev_count)):
            gpus.append(
                {
                    "name": f"GPU {i} (via driver devices)",
                    "memory_total_mib": 0,
                    "memory_used_mib": 0,
                    "driver_version": driver_ver,
                    "compute_capability": "5.2" if has_proc else "0",
                }
            )
        reason = f"GPU devices present ({dev_count} device(s), driver {driver_ver}) — nvidia-smi binary not in PATH, but /dev/nvidia* / /proc/driver/nvidia present. Visible={visible or '<unset>'}"
        return {
            "present": True,
            "gpus": gpus,
            "vllm_supported": False,
            "ollama_supported": True,
            "reason": reason,
            "fallback": True,
        }
    return None


def detect() -> dict:
    if shutil.which("nvidia-smi") is None:
        fb = _fallback_from_proc()
        if fb is not None:
            return fb
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
        fb = _fallback_from_proc()
        if fb is not None:
            fb["reason"] = f"{fb['reason']} (nvidia-smi error: {exc})"
            return fb
        return {"present": False, "reason": str(exc)}
    if out.returncode != 0:
        fb = _fallback_from_proc()
        if fb is not None:
            fb["reason"] = f"{fb['reason']} (nvidia-smi failed: {out.stderr.strip()})"
            return fb
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
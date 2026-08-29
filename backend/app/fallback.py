"""CPU-only fallback responder for Stage 1 (before the local engine is wired in
Stage 2). Deterministic, fully offline, no model required."""

from __future__ import annotations


class CPUFallback:
    def respond(self, message: str) -> str:
        msg = (message or "").strip().lower()
        if not msg:
            return "I didn't catch that — try 'help'."

        if msg in {"help", "/help", "?"}:
            return (
                "hivestack local fallback (Stage 1) — no model attached yet.\n"
                "- 'status'  — what's configured\n"
                "- anything else — echoed back as a stub reply"
            )
        if msg in {"status", "/status"}:
            return (
                "Local fallback online. Providers and modules can be toggled in Settings; "
                "GPU status is on the dashboard. A real model attaches in Stage 2."
            )
        if "hello" in msg or "hi" in msg:
            return "Hello! This is the CPU fallback responder — a model lands here in Stage 2."
        return (
            f"[local fallback] I got: {message[:500]!r}. "
            "No model is configured yet (Stage 2 wires the local Ollama engine and optional cloud providers)."
        )


fallback = CPUFallback()
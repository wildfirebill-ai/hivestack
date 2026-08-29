"""Provider gate helpers — the single choke point for provider access."""

from __future__ import annotations

import os

from fastapi import HTTPException

from .config import settings


def _has_key(provider: dict) -> bool:
    key_env = provider.get("key_env")
    if not key_env:
        return True  # local engine or no key required
    return bool(os.getenv(key_env))


def list_providers() -> list[dict]:
    items = settings.providers()
    for p in items:
        p["allowed"] = settings.provider_is_allowed(p.get("name", ""))
        p["has_key"] = _has_key(p)
    return items


def require_allowed(name: str) -> dict:
    provider = settings.get_provider(name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"unknown provider '{name}'")
    if not settings.provider_is_allowed(name):
        reason = "offline mode is on" if settings.offline_mode else "provider is disabled"
        raise HTTPException(status_code=403, detail=f"provider '{name}' not allowed: {reason}")
    return provider
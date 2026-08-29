"""Health / readiness probes (Docker HEALTHCHECK + Unraid uptime)."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "name": settings.name,
        "version": settings.version,
        "offline_mode": settings.offline_mode,
    }
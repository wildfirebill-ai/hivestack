"""Health / readiness probes (Docker HEALTHCHECK + Unraid uptime)."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..db import _conn
from ..log import get_logger

router = APIRouter(tags=["health"])
_log = get_logger("health")


def _db_ok() -> str | None:
    try:
        with _conn() as con:
            con.execute("SELECT 1").fetchone()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


@router.get("/health")
def health() -> dict:
    """Liveness — the process is up."""
    return {
        "status": "ok",
        "name": settings.name,
        "version": settings.version,
        "offline_mode": settings.offline_mode,
    }


@router.get("/health/ready")
def ready() -> dict:
    """Readiness — core subsystems (DB, modules) are usable.

    Used by the Docker HEALTHCHECK / orchestrators; returns 503 if the DB is
    unreachable so the container is restarted instead of serving pointless 500s.
    """
    ts = time.time()
    report: dict = {
        "ready": True,
        "database": "ok",
        "modules": settings.modules(),
        "offline_mode": settings.offline_mode,
        "generated_at_ts": ts,
    }
    db_err = _db_ok()
    if db_err:
        report["ready"] = False
        report["database"] = f"error: {db_err}"
        _log.error("readiness failed", extra={"database": db_err})
    if not report["ready"]:
        reply = {**report, "status": "not_ready"}
        raise HTTPException(status_code=503, detail=reply)
    report["status"] = "ready"
    return report

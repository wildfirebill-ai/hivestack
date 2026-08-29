"""System settings surface — offline switch, provider toggles, module toggles, GPU."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import providers, security
from ..config import settings
from ..db import _conn
from ..gpu import detect as gpu_detect

router = APIRouter(prefix="/api/system", tags=["system"])
_auth = Depends(security.require_token)


class ToggleIn(BaseModel):
    enabled: bool


@router.get("")
def system_info(_: str = _auth) -> dict:
    return {
        "name": settings.name,
        "version": settings.version,
        "offline_mode": settings.offline_mode,
    }


@router.post("/offline")
def set_offline(body: ToggleIn, user: str = _auth) -> dict:
    settings.set_offline_mode(body.enabled)
    from .. import governance

    governance.audit(user, "offline.set", None, {"offline_mode": body.enabled})
    return {"offline_mode": settings.offline_mode}


@router.get("/providers")
def get_providers(_: str = _auth) -> dict:
    return {
        "offline_mode": settings.offline_mode,
        "providers": providers.list_providers(),
    }


@router.post("/providers/{name}")
def toggle_provider(name: str, body: ToggleIn, user: str = _auth) -> dict:
    provider = settings.set_provider_enabled(name, body.enabled)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"unknown provider '{name}'")
    provider["allowed"] = settings.provider_is_allowed(name)
    from .. import governance

    governance.audit(user, "provider.toggle", name, {"enabled": body.enabled})
    return {"provider": provider}


@router.get("/modules")
def get_modules(_: str = _auth) -> dict:
    return {"modules": settings.modules()}


@router.post("/modules/{name}")
def toggle_module(name: str, body: ToggleIn, user: str = _auth) -> dict:
    try:
        settings.set_module_enabled(name, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown module '{name}'") from None
    from .. import governance

    governance.audit(user, "module.toggle", name, {"enabled": body.enabled})
    return {"name": name, "enabled": settings.module_enabled(name)}


@router.get("/gpu")
def get_gpu(_: str = _auth) -> dict:
    return gpu_detect()


@router.get("/usage")
def usage(days: float | None = None, _: str = _auth) -> dict:
    """Token + estimated cost usage. `days` optionally returns a per-day series."""
    from ..governance import budget_config

    cfg = budget_config()
    cost_in = cfg["cost_per_1k_in"]
    cost_out = cfg["cost_per_1k_out"]

    with _conn() as con:
        rows = con.execute(
            "SELECT COALESCE(provider,'n/a') AS provider, COALESCE(model,'n/a') AS model,"
            " COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS in_tok,"
            " COALESCE(SUM(output_tokens),0) AS out_tok"
            " FROM messages WHERE role='assistant'"
            " GROUP BY provider, model ORDER BY calls DESC"
        ).fetchall()
        totals = con.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS in_tok,"
            " COALESCE(SUM(output_tokens),0) AS out_tok"
            " FROM messages WHERE role='assistant'"
        ).fetchone()
    totals = dict(totals)
    breakdown = []
    for r in rows:
        b = dict(r)
        b["est_cost_usd"] = round(
            (b["in_tok"] / 1000.0) * cost_in + (b["out_tok"] / 1000.0) * cost_out, 6
        )
        breakdown.append(b)

    result: dict = {
        "breakdown": breakdown,
        "totals": {**totals, "est_cost_usd": round(
            (totals["in_tok"] / 1000.0) * cost_in + (totals["out_tok"] / 1000.0) * cost_out, 6
        )},
    }

    if days is not None:
        with _conn() as con:
            series = con.execute(
                "SELECT date(created_at) AS day, COUNT(*) AS calls,"
                " COALESCE(SUM(input_tokens),0) AS in_tok, COALESCE(SUM(output_tokens),0) AS out_tok"
                " FROM messages WHERE role='assistant' AND created_at >= datetime('now', ?)"
                " GROUP BY date(created_at) ORDER BY day",
                (f"-{int(days)} days",),
            ).fetchall()
        result["series"] = [
            {**dict(s), "est_cost_usd": round(
                (s["in_tok"] / 1000.0) * cost_in + (s["out_tok"] / 1000.0) * cost_out, 6
            )}
            for s in series
        ]
    return result
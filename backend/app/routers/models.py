"""Model registry — list/add/remove/toggle/default, ping, and Ollama pull (async)."""

from __future__ import annotations

import json
import threading

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..providers import list_providers

router = APIRouter(prefix="/api/models", tags=["models"])
_auth = Depends(security.require_token)


class ModelIn(BaseModel):
    name: str
    provider: str = "ollama"
    model_id: str | None = None
    family: str = "other"
    context: int = 8192
    enabled: bool = True
    notes: str = ""


class ToggleIn(BaseModel):
    enabled: bool


class DefaultIn(BaseModel):
    provider: str
    model: str | None = None


class PullIn(BaseModel):
    provider: str = "ollama"
    model_id: str


class PullStatusIn(BaseModel):
    provider: str = "ollama"
    model_id: str


def _enrich(model: dict) -> dict:
    out = dict(model)
    out["provider_allowed"] = settings.provider_is_allowed(model.get("provider", ""))
    out["is_default"] = (
        settings.default_model and settings.default_model.lower() == model.get("name", "").lower()
    )
    return out


@router.get("")
def list_models(_: str = _auth) -> dict:
    return {
        "models": [_enrich(m) for m in settings.models()],
        "default_provider": settings.default_provider or "ollama",
        "default_model": settings.default_model or "",
        "providers": list_providers(),
    }


@router.post("")
def add_model(body: ModelIn, _: str = _auth) -> dict:
    entry = {
        "name": body.name.strip(),
        "provider": body.provider.strip().lower(),
        "model_id": (body.model_id or body.name).strip(),
        "family": body.family or "other",
        "context": body.context or 8192,
        "enabled": body.enabled,
        "notes": body.notes,
    }
    if settings.get_provider(entry["provider"]) is None:
        raise HTTPException(status_code=404, detail=f"unknown provider '{entry['provider']}'")
    try:
        saved = settings.add_model(entry)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"model": _enrich(saved)}


@router.delete("/{name}")
def remove_model(name: str, _: str = _auth) -> dict:
    if not settings.remove_model(name):
        raise HTTPException(status_code=404, detail=f"unknown model '{name}'")
    return {"removed": name}


@router.post("/{name}/enabled")
def toggle_model(name: str, body: ToggleIn, _: str = _auth) -> dict:
    saved = settings.set_model_enabled(name, body.enabled)
    if saved is None:
        raise HTTPException(status_code=404, detail=f"unknown model '{name}'")
    return {"model": _enrich(saved)}


@router.post("/default")
def set_default(body: DefaultIn, _: str = _auth) -> dict:
    if settings.get_provider(body.provider) is None:
        raise HTTPException(status_code=404, detail=f"unknown provider '{body.provider}'")
    if body.model and settings.get_model(body.model) is None:
        raise HTTPException(status_code=404, detail=f"unknown model '{body.model}'")
    settings.set_default_model(body.provider, body.model)
    return {
        "default_provider": settings.default_provider or body.provider,
        "default_model": settings.default_model or "",
    }


@router.post("/{name}/test")
def test_model(name: str, _: str = _auth) -> dict:
    model = settings.get_model(name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"unknown model '{name}'")
    provider = settings.get_provider(model["provider"])
    assert provider is not None
    base = (provider.get("base_url") or "").rstrip("/")
    if model["provider"] == "ollama":
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(base + "/api/tags")
            tags = r.json().get("models", []) if r.status_code == 200 else []
            have = any(t.get("name", "").split(":")[0] == model["model_id"].split(":")[0] for t in tags)
            return {"tested": True, "reachable": True, "installed": have, "detail": f"{len(tags)} model(s) in Ollama"}
        except httpx.HTTPError as exc:
            return {"tested": True, "reachable": False, "installed": False, "detail": str(exc)}
    return {
        "tested": False,
        "reachable": None,
        "installed": None,
        "detail": f"ping is implemented for local engines; '{model['provider']}' is gate-checked instead",
    }


# ---------------------------------------------------------------- ollama pull
_pull_lock = threading.Lock()
_pull_status: dict[str, dict] = {}


def _pull_key(provider: str, model_id: str) -> str:
    return f"{provider}|{model_id}"


@router.post("/pull")
def pull_model(body: PullIn, _: str = _auth) -> dict:
    key = _pull_key(body.provider, body.model_id)
    with _pull_lock:
        if _pull_status.get(key, {}).get("state") == "running":
            raise HTTPException(status_code=409, detail="a pull for this model is already running")
        _pull_status[key] = {"state": "running", "progress": "starting", "error": None}

    def _run() -> None:
        provider = settings.get_provider(body.provider)
        try:
            if provider is None:
                raise RuntimeError(f"unknown provider '{body.provider}'")
            base = (provider.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
            with httpx.Client(timeout=None) as client:
                with client.stream("POST", base + "/api/pull", json={"model": body.model_id, "stream": True}) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        status = obj.get("status", "")
                        completed, total = obj.get("completed", 0), obj.get("total", 0)
                        pct = f"{completed / total * 100:.0f}%" if total else status
                        with _pull_lock:
                            _pull_status[key]["progress"] = f"{status} {pct if total else ''}".strip()
            with _pull_lock:
                _pull_status[key]["state"] = "done"
                _pull_status[key]["progress"] = "complete"
        except Exception as exc:  # noqa: BLE001
            with _pull_lock:
                _pull_status[key]["state"] = "error"
                _pull_status[key]["error"] = str(exc)

    threading.Thread(target=_run, daemon=True).start()
    return {"accepted": True, "provider": body.provider, "model_id": body.model_id}


@router.get("/pull/status")
def pull_status(provider: str = "ollama", model_id: str = "") -> dict:
    key = _pull_key(provider, model_id)
    status = _pull_status.get(key)
    if status is None:
        raise HTTPException(status_code=404, detail="no pull started for this model")
    return status
"""Skills & packaging endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..skills import generator, store

router = APIRouter(prefix="/api/skills", tags=["skills"])
_auth = Depends(security.require_token)


def _require_module() -> None:
    if not settings.module_enabled("skills"):
        raise HTTPException(status_code=403, detail="skills module is disabled")


class SkillIn(BaseModel):
    name: str
    description: str = ""
    instructions: str
    tags: list[str] | None = None
    version: str = "1.0.0"


class GenerateIn(BaseModel):
    description: str
    name: str | None = None
    use_llm: bool = True


class EvalIn(BaseModel):
    probe: str = ""  # goal for a trial agent run; empty → use skill description


@router.get("")
def list_skills(_: str = _auth) -> dict:
    return {"skills": store.list_skills()}


@router.get("/{name}")
def get_skill(name: str, _: str = _auth) -> dict:
    skill = store.get_skill(name)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"skill": skill}


@router.post("")
def create_skill(body: SkillIn, _: str = _auth) -> dict:
    _require_module()
    try:
        skill = store.add_skill(body.name, body.description, body.instructions, body.tags, body.version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"skill": skill}


@router.post("/generate")
def generate_skill(body: GenerateIn, _: str = _auth) -> dict:
    _require_module()
    if not (body.description or "").strip():
        raise HTTPException(status_code=422, detail="description required")
    skill = generator.generate(body.name, body.description, use_llm=body.use_llm)
    return {"skill": skill}


@router.post("/{name}/validate")
def validate(name: str, _: str = _auth) -> dict:
    try:
        return store.validate(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{name}/eval")
def eval_skill(name: str, body: EvalIn, _: str = _auth) -> dict:
    _require_module()
    skill = store.get_skill(name)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    from ..agents import runtime

    goal = (body.probe or (skill.get("description") or "")).strip()
    if not goal:
        raise HTTPException(status_code=422, detail="eval needs a probe goal")
    rid = runtime.create(goal=goal, skill=name, max_steps=8, allowed_scopes=["low", "medium"])
    runtime.start(rid)
    for _ in range(120):
        s = runtime.task_summary(rid)
        if s and s["status"] in ("completed", "error", "cancelled"):
            break
        import time

        time.sleep(0.5)
    detail = runtime.task_detail(rid)
    return {"eval_run": rid, "status": detail["status"] if detail else "unknown",
            "steps": len(detail.get("events", [])) if detail else 0,
            "tokens_in": detail.get("tokens_in", 0) if detail else 0,
            "tokens_out": detail.get("tokens_out", 0) if detail else 0}


@router.get("/{name}/export")
def export(name: str, _: str = _auth) -> dict:
    try:
        return store.export(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.delete("/{name}")
def delete(name: str, _: str = _auth) -> dict:
    if not store.delete_skill(name):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"removed": name}


@router.post("/{name}/quarantine")
def quarantine(name: str, _: str = _auth) -> dict:
    if not store.set_status(name, "quarantined"):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"name": name, "status": "quarantined"}


# ---------------------------------------------------------------- packaging
class InstallIn(BaseModel):
    kind: str  # local | git
    ref: str
    label: str | None = None


@router.post("/install")
def install(body: InstallIn, _: str = _auth) -> dict:
    _require_module()
    if body.kind == "git" and settings.offline_mode:
        raise HTTPException(status_code=403, detail="git install is a network call — offline mode is on")
    if body.kind not in ("local", "git"):
        raise HTTPException(status_code=422, detail="kind must be local or git")
    try:
        return store.install(body.kind, body.ref, body.label)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"install failed: {exc}") from None


@router.get("/sources/list")
def sources(_: str = _auth) -> dict:
    return {"sources": store.sync_states()}
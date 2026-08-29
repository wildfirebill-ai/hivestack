"""Agent task endpoints — create runs, list/detail, cancel, tool registry."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..agents import runtime
from ..agents.tools import execute_tool, registry
from ..config import settings

router = APIRouter(prefix="/api/agents", tags=["agents"])
_auth = Depends(security.require_token)


class TaskIn(BaseModel):
    goal: str
    name: str = ""
    provider: str | None = None
    model: str | None = None
    max_steps: int = 10
    allowed_scopes: list[str] | None = None
    auto: str = "auto"


class ToolRunIn(BaseModel):
    args: dict = {}
    allowed_scopes: list[str] | None = None


def _require_module() -> None:
    if not settings.module_enabled("agents"):
        raise HTTPException(status_code=403, detail="agents module is disabled")


@router.post("/tasks")
def create_task(body: TaskIn, _: str = _auth) -> dict:
    _require_module()
    goal = (body.goal or "").strip()
    if not goal:
        raise HTTPException(status_code=422, detail="goal is empty")
    scopes = body.allowed_scopes if body.allowed_scopes is not None else ["low", "medium"]
    for s in scopes:
        if s not in ("low", "medium", "high"):
            raise HTTPException(status_code=422, detail=f"unknown scope '{s}'")
    run_id = runtime.create(
        goal=goal,
        name=body.name,
        provider=body.provider,
        model=body.model,
        max_steps=body.max_steps,
        allowed_scopes=scopes,
        auto=body.auto,
    )
    runtime.start(run_id)
    return runtime.task_summary(run_id) or {"id": run_id}


@router.get("/tasks")
def list_tasks(_: str = _auth) -> dict:
    from ..db import _conn

    with _conn() as con:
        rows = con.execute(
            "SELECT id,name,goal,status,provider,model,tokens_in,tokens_out,error,created_at,updated_at"
            " FROM tasks ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return {"tasks": [dict(r) for r in rows]}


@router.get("/tasks/{run_id}")
def task_detail(run_id: str, _: str = _auth) -> dict:
    detail = runtime.task_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.post("/tasks/{run_id}/cancel")
def cancel_task(run_id: str, _: str = _auth) -> dict:
    if runtime.task_summary(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    runtime.cancel(run_id)
    return {"cancelled": run_id}


@router.get("/tools")
def list_tools(_: str = _auth) -> dict:
    return {
        "tools": [
            {"name": t.name, "description": t.desc, "scope": t.scope, "network": t.requires_network,
             "args_schema": t.args_schema}
            for t in registry.all()
        ],
        "offline_mode": settings.offline_mode,
    }


@router.post("/tools/{name}/run")
def run_tool(name: str, body: ToolRunIn, _: str = _auth) -> dict:
    tool = registry.get(name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"unknown tool '{name}'")
    policy = {"allowed_scopes": body.allowed_scopes or ["low", "medium", "high"], "auto": "auto"}
    output, err = execute_tool(tool, body.args or {}, policy)
    return {"tool": name, "output": output, "error": err, "denied": err is not None}
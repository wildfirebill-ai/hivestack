"""Workflow + schedule endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..workflows import engine, scheduler

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
_auth = Depends(security.require_token)


def _require_module() -> None:
    if not settings.module_enabled("workflow"):
        raise HTTPException(status_code=403, detail="workflow module is disabled")


class WorkflowIn(BaseModel):
    name: str
    definition: dict


class RunIn(BaseModel):
    inputs: dict = {}


class ApproveIn(BaseModel):
    approve: bool
    note: str = ""


class ScheduleIn(BaseModel):
    workflow_id: str
    kind: str
    value: str
    enabled: bool = True


# ---------------------------------------------------------------- workflows
@router.get("")
def list_workflows(_: str = _auth) -> dict:
    return {"workflows": engine.list_workflows()}


@router.post("")
def create_workflow(body: WorkflowIn, _: str = _auth) -> dict:
    _require_module()
    steps = body.definition.get("steps", [])
    if not steps:
        raise HTTPException(status_code=422, detail="definition needs at least one step")
    wid = engine.create_workflow(body.name, body.definition)
    wf = engine.get_workflow(wid)
    return {"workflow": {**wf, "definition": wf["definition"]}}


@router.get("/{wid}")
def get_workflow(wid: str, _: str = _auth) -> dict:
    wf = engine.get_workflow(wid)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"workflow": wf}


@router.delete("/{wid}")
def delete_workflow(wid: str, _: str = _auth) -> dict:
    if not engine.delete_workflow(wid):
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"removed": wid}


@router.post("/{wid}/run")
def run_workflow(wid: str, _body: RunIn | None = None, _: str = _auth) -> dict:
    _require_module()
    try:
        run_id = engine.start_run(wid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"run_id": run_id, "workflow_id": wid}


# ---------------------------------------------------------------- runs
@router.get("/runs/list")
def list_runs(_: str = _auth) -> dict:
    return {"runs": engine.list_runs()}


@router.get("/runs/{run_id}")
def get_run(run_id: str, _: str = _auth) -> dict:
    detail = engine.run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, body: ApproveIn, _: str = _auth) -> dict:
    try:
        return engine.approve(run_id, body.approve, body.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str, _: str = _auth) -> dict:
    try:
        return engine.resume(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, _: str = _auth) -> dict:
    engine.cancel(run_id)
    return {"run_id": run_id}


# ---------------------------------------------------------------- schedules
@router.get("/schedules/list")
def list_schedules(_: str = _auth) -> dict:
    return {"schedules": scheduler.list_schedules()}


@router.post("/schedules")
def create_schedule(body: ScheduleIn, _: str = _auth) -> dict:
    _require_module()
    try:
        s = scheduler.create_schedule(body.workflow_id, body.kind, body.value, body.enabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"schedule": s}


@router.delete("/schedules/{sid}")
def delete_schedule(sid: str, _: str = _auth) -> dict:
    if not scheduler.delete_schedule(sid):
        raise HTTPException(status_code=404, detail="schedule not found")
    return {"removed": sid}
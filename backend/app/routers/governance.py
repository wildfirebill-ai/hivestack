"""Governance endpoints — RBAC users, budgets, audit, dashboard, security review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import governance, security
from ..config import settings

router = APIRouter(prefix="/api/governance", tags=["governance"])
_auth = Depends(security.require_token)


def _require() -> None:
    if not settings.module_enabled("governance"):
        raise HTTPException(status_code=403, detail="governance module is disabled")


class UserIn(BaseModel):
    name: str
    password: str
    role: str = "viewer"


class RoleIn(BaseModel):
    role: str


class BudgetIn(BaseModel):
    enabled: bool | None = None
    budget_enabled: bool | None = None
    daily_token_budget: int | None = None
    per_run_token_limit: int | None = None
    cost_per_1k_in: float | None = None
    cost_per_1k_out: float | None = None


@router.get("")
def overview(_: str = _auth) -> dict:
    return {"enabled": settings.module_enabled("governance"), "budget": governance.budget_config()}


# ------------------------------------------------------------------ users
@router.get("/users")
def users(user: str = Depends(security.require_admin)) -> dict:
    return {"users": governance.list_users(), "current": user}


@router.post("/users")
def create_user(body: UserIn, user: str = Depends(security.require_admin)) -> dict:
    _require()
    try:
        name = governance.add_user(body.name, body.role, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    governance.audit(user, "user.create", name, {"role": body.role})
    return {"created": name}


@router.post("/users/{name}/role")
def update_role(name: str, body: RoleIn, user: str = Depends(security.require_admin)) -> dict:
    try:
        ok = governance.set_role(name, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not ok:
        raise HTTPException(status_code=404, detail="user not found")
    governance.audit(user, "user.role", name, {"role": body.role})
    return {"name": name, "role": body.role}


@router.delete("/users/{name}")
def delete_user(name: str, user: str = Depends(security.require_admin)) -> dict:
    try:
        ok = governance.remove_user(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not ok:
        raise HTTPException(status_code=404, detail="user not found")
    governance.audit(user, "user.delete", name, {})
    return {"removed": name}


# ------------------------------------------------------------------ budgets
@router.get("/budget")
def budget(_: str = _auth) -> dict:
    return {"config": governance.budget_config(), "usage": governance.today_usage()}


@router.post("/budget")
def update_budget(body: BudgetIn, user: str = Depends(security.require_admin)) -> dict:
    _require()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = governance.set_budget_config(**updates)
    governance.audit(user, "budget.update", None, updates)
    return {"config": cfg, "usage": governance.today_usage()}


# ------------------------------------------------------------------ audit / dashboard / security
@router.get("/audit")
def audit_log(_: str = _auth, limit: int = 200) -> dict:
    return {"entries": governance.list_audit(limit)}


@router.get("/dashboard")
def dashboard(_: str = _auth) -> dict:
    return governance.dashboard()


@router.get("/security-review")
def security_review(_: str = _auth) -> dict:
    return governance.security_review()


# ------------------------------------------------------------------ verification gate
@router.post("/verify/{run_id}")
def verify(run_id: str, _: str = _auth) -> dict:
    try:
        return governance.verify_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
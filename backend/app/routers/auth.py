"""Login — per-username, RBAC-aware. Admin seeded from env on first boot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = "admin"
    password: str


@router.post("/login")
def do_login(body: LoginIn) -> dict:
    token = security.login(body.username, body.password)
    if token is None:
        raise HTTPException(status_code=401, detail="bad credentials")
    return {"token": token, "user": body.username}


@router.get("/me")
def me(user: str = Depends(security.require_token)) -> dict:
    from .. import governance

    return {"user": user, "role": governance.role_of(user)}
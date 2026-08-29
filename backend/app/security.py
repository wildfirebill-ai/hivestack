"""Authentication — per-user login (governance RBAC), bearer tokens with TTL,
admin-only dependency."""

from __future__ import annotations

import secrets
import threading
import time

from fastapi import Depends, HTTPException, Request

from . import governance
from .config import settings
from .db import init_db

_TOKEN_TTL_SECONDS = 12 * 3600
_tokens: dict[str, tuple[str, float]] = {}  # token -> (username, issued_at)
_lock = threading.Lock()


def login(username: str, password: str) -> str | None:
    init_db()
    governance.seed_admin()
    user = governance.auth(username, password)
    if user is None:
        return None
    token = "hivestack." + secrets.token_urlsafe(32)
    with _lock:
        _tokens[token] = (username, time.time())
    return token


def _purge() -> None:
    now = time.time()
    with _lock:
        for token in [t for t, (_, ts) in _tokens.items() if now - ts > _TOKEN_TTL_SECONDS]:
            _tokens.pop(token, None)


def authorize(authorization: str | None) -> str:
    _purge()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:].strip()
    with _lock:
        if token not in _tokens:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        username = _tokens[token][0]
    return username


async def require_token(request: Request) -> str:
    return authorize(request.headers.get("authorization"))


def require_role(allowed: set[str]):
    async def dependency(request: Request) -> str:
        username = authorize(request.headers.get("authorization"))
        role = governance.role_of(username)
        if role not in allowed:
            raise HTTPException(status_code=403, detail=f"requires role in {sorted(allowed)}")
        return username

    return dependency


require_admin = require_role({"admin"})
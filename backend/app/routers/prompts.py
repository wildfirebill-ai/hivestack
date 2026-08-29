"""Prompt studio — named system prompts selectable per chat."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..config import settings

router = APIRouter(prefix="/api/prompts", tags=["prompts"])
_auth = Depends(security.require_token)


class PromptIn(BaseModel):
    name: str
    system: str


@router.get("")
def list_prompts(_: str = _auth) -> dict:
    return {"prompts": settings.prompts()}


@router.post("")
def add_prompt(body: PromptIn, _: str = _auth) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="prompt needs a name")
    settings.add_prompt(name, body.system)
    return {"prompt": {"name": name, "system": body.system}}


@router.delete("/{name}")
def remove_prompt(name: str, _: str = _auth) -> dict:
    if not settings.remove_prompt(name):
        raise HTTPException(status_code=404, detail=f"unknown prompt '{name}'")
    return {"removed": name}
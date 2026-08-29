"""Kanban board endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..workflows import boards as _boards

router = APIRouter(prefix="/api/boards", tags=["boards"])
_auth = Depends(security.require_token)


def _require_module() -> None:
    if not settings.module_enabled("workflow"):
        raise HTTPException(status_code=403, detail="workflow (boards) module is disabled")


class BoardIn(BaseModel):
    name: str


class ColumnIn(BaseModel):
    name: str


class CardIn(BaseModel):
    column: str = "Todo"
    title: str
    body: str = ""
    run_id: str | None = None


class MoveIn(BaseModel):
    column_id: str


@router.get("")
def list_boards(_: str = _auth) -> dict:
    return {"boards": _boards.list_boards()}


@router.post("")
def create_board(body: BoardIn, _: str = _auth) -> dict:
    _require_module()
    return {"id": _boards.create_board(body.name)}


@router.get("/{bid}")
def get_board(bid: str, _: str = _auth) -> dict:
    b = _boards.board_detail(bid)
    if b is None:
        raise HTTPException(status_code=404, detail="board not found")
    return b


@router.delete("/{bid}")
def delete_board(bid: str, _: str = _auth) -> dict:
    if not _boards.delete_board(bid):
        raise HTTPException(status_code=404, detail="board not found")
    return {"removed": bid}


@router.post("/{bid}/columns")
def add_column(bid: str, body: ColumnIn, _: str = _auth) -> dict:
    try:
        return _boards.add_column(bid, body.name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{bid}/cards")
def add_card(bid: str, body: CardIn, _: str = _auth) -> dict:
    try:
        card_id = _boards.add_card(bid, body.column, body.title, body.body, body.run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"card_id": card_id}


@router.post("/cards/{card_id}/move")
def move_card(card_id: str, body: MoveIn, _: str = _auth) -> dict:
    if not _boards.move_card(card_id, body.column_id):
        raise HTTPException(status_code=404, detail="card not found")
    return {"moved": card_id}


@router.delete("/cards/{card_id}")
def delete_card(card_id: str, _: str = _auth) -> dict:
    if not _boards.delete_card(card_id):
        raise HTTPException(status_code=404, detail="card not found")
    return {"removed": card_id}
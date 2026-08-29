"""Kanban boards — columns + cards, optionally linked to workflow runs."""

from __future__ import annotations

import uuid
from typing import Any

from ..db import _conn

DEFAULT_COLUMNS = ["Backlog", "Todo", "In Progress", "Review", "Done"]


def _row(sql: str, params: tuple = ()) -> dict | None:
    with _conn() as con:
        r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def create_board(name: str) -> str:
    bid = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute("INSERT INTO boards(id, name) VALUES (?,?)", (bid, name))
        for i, col in enumerate(DEFAULT_COLUMNS):
            con.execute("INSERT INTO board_columns(id, board_id, name, position) VALUES (?,?,?,?)",
                        (uuid.uuid4().hex[:12], bid, col, i))
    return bid


def board_detail(bid: str) -> dict | None:
    row = _row("SELECT * FROM boards WHERE id=?", (bid,))
    if row is None:
        return None
    with _conn() as con:
        cols = con.execute("SELECT * FROM board_columns WHERE board_id=? ORDER BY position, name", (bid,)).fetchall()
    columns = []
    for c in cols:
        with _conn() as con:
            cards = con.execute(
                "SELECT * FROM board_cards WHERE column_id=? ORDER BY position, created_at DESC", (c["id"],)
            ).fetchall()
        columns.append({**dict(c), "cards": [dict(x) for x in cards]})
    row["columns"] = columns
    return row


def list_boards() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT id, name, created_at FROM boards ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        with _conn() as con:
            cnt = con.execute("SELECT COUNT(*) AS n FROM board_cards WHERE column_id IN (SELECT id FROM board_columns WHERE board_id=?)", (r["id"],)).fetchone()["n"]
        out.append({**dict(r), "cards": cnt})
    return out


def delete_board(bid: str) -> bool:
    with _conn() as con:
        con.execute("DELETE FROM board_cards WHERE column_id IN (SELECT id FROM board_columns WHERE board_id=?)", (bid,))
        con.execute("DELETE FROM board_columns WHERE board_id=?", (bid,))
        cur = con.execute("DELETE FROM boards WHERE id=?", (bid,))
    return cur.rowcount > 0


def add_column(bid: str, name: str) -> dict:
    if board_detail(bid) is None:
        raise LookupError("board not found")
    cid = uuid.uuid4().hex[:12]
    with _conn() as con:
        pos = con.execute("SELECT COALESCE(MAX(position),0)+1 AS p FROM board_columns WHERE board_id=?", (bid,)).fetchone()["p"]
        con.execute("INSERT INTO board_columns(id, board_id, name, position) VALUES (?,?,?,?)", (cid, bid, name, pos))
    return {"id": cid, "board_id": bid, "name": name}


def _column_id(bid: str, column: str) -> str | None:
    with _conn() as con:
        r = con.execute("SELECT id FROM board_columns WHERE board_id=? AND lower(name)=lower(?)", (bid, column)).fetchone()
    return r["id"] if r else None


def add_card(board_id: str, column: str, title: str, body: str = "", run_id: str | None = None) -> str:
    cid = _column_id(board_id, column)
    if cid is None:
        # create the column on the fly
        cid = add_column(board_id, column)["id"]
    card_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        pos = con.execute("SELECT COALESCE(MAX(position),0)+1 AS p FROM board_cards WHERE column_id=?", (cid,)).fetchone()["p"]
        con.execute(
            "INSERT INTO board_cards(id, column_id, title, body, run_id, position) VALUES (?,?,?,?,?,?)",
            (card_id, cid, title, body, run_id, pos),
        )
    return card_id


def move_card(card_id: str, column_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE board_cards SET column_id=?, position=(SELECT COALESCE(MAX(position),0)+1 FROM board_cards WHERE column_id=?) WHERE id=?",
                          (column_id, column_id, card_id))
    return cur.rowcount > 0


def delete_card(card_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM board_cards WHERE id=?", (card_id,))
    return cur.rowcount > 0
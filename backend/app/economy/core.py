"""Economy core — accounts, gig marketplace, escrow settlement, ledger."""

from __future__ import annotations

import uuid

from ..db import _conn


def accounts() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM economy_accounts ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_account(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM economy_accounts WHERE name=?", (name,)).fetchone()
    return dict(row) if row else None


def create_account(name: str, kind: str = "user", seed: float = 0.0) -> dict:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO economy_accounts(name, kind, balance) VALUES (?,?,?)",
            (name, kind, float(seed)),
        )
    return get_account(name)  # type: ignore[return-value]


def _transfer(src: str, dst: str, amount: float, ref: str, note: str) -> None:
    with _conn() as con:
        s = con.execute("SELECT balance FROM economy_accounts WHERE name=?", (src,)).fetchone()
        if s is None:
            raise LookupError(f"account '{src}' not found")
        if s["balance"] < amount:
            raise ValueError(f"insufficient balance in '{src}' ({s['balance']} < {amount})")
        con.execute("UPDATE economy_accounts SET balance=balance-? WHERE name=?", (amount, src))
        con.execute("UPDATE economy_accounts SET balance=balance+? WHERE name=?", (amount, dst))
        con.execute("INSERT INTO economy_ledger(src, dst, amount, ref, note) VALUES (?,?,?,?,?)",
                    (src, dst, amount, ref, note))


def gigs(status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM economy_gigs"
    params: list = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT 100"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def create_gig(title: str, reward: float, owner: str) -> str:
    if get_account(owner) is None:
        create_account(owner, kind="user", seed=0.0)
    gig_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO economy_gigs(id, title, reward, owner) VALUES (?,?,?,?)",
            (gig_id, title, float(reward), owner),
        )
    return gig_id


def claim(gig_id: str, performer: str) -> dict:
    gig = _get(gig_id)
    if gig["status"] != "open":
        raise ValueError(f"gig is {gig['status']}, not open")
    if get_account(performer) is None:
        create_account(performer, kind="agent", seed=0.0)
    with _conn() as con:
        con.execute(
            "UPDATE economy_gigs SET performer=?, status='claimed', updated_at=datetime('now') WHERE id=?",
            (performer, gig_id),
        )
    return _get(gig_id)  # type: ignore[return-value]


def complete(gig_id: str) -> dict:
    gig = _get(gig_id)
    if gig["status"] != "claimed":
        raise ValueError(f"gig is {gig['status']} — must be claimed first")
    with _conn() as con:
        con.execute("UPDATE economy_gigs SET status='completed', updated_at=datetime('now') WHERE id=?", (gig_id,))
    return _get(gig_id)  # type: ignore[return-value]


def settle(gig_id: str, approver: str) -> dict:
    """Approve settlement: escrow reward moves owner → performer, reputation bumps."""
    gig = _get(gig_id)
    if gig["status"] not in ("completed", "claimed"):
        raise ValueError(f"gig is {gig['status']} — not payable")
    performer = gig["performer"] or approver
    _transfer(gig["owner"], performer, gig["reward"], ref=f"gig:{gig_id}", note=f"settlement for '{gig['title']}'")
    with _conn() as con:
        con.execute("UPDATE economy_gigs SET status='paid', updated_at=datetime('now') WHERE id=?", (gig_id,))
        con.execute("UPDATE economy_accounts SET reputation=reputation+1 WHERE name=?", (performer,))
    gig = _get(gig_id)
    gig["paid_to"] = performer  # type: ignore[assignment]
    return gig


def ledger(limit: int = 100) -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM economy_ledger ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def _get(gig_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM economy_gigs WHERE id=?", (gig_id,)).fetchone()
    return dict(row) if row else None
"""Encrypted secrets vault — values encrypted at rest with Fernet (AES-128-CBC +
HMAC). Master key from env HIVESTACK_VAULT_KEY or a generated keyfile in /data."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .db import _conn

_f = None


def _fernet() -> Fernet:
    global _f
    if _f is not None:
        return _f
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    env_key = os.getenv("HIVESTACK_VAULT_KEY")
    if env_key:
        _f = Fernet(env_key.encode())
        return _f
    key_file = settings.data_dir / "vault.key"
    if key_file.exists():
        _f = Fernet(key_file.read_bytes())
    else:
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        _f = Fernet(key)
    return _f


def set_secret(name: str, value: str) -> None:
    token = _fernet().encrypt(value.encode())
    with _conn() as con:
        con.execute(
            "INSERT INTO vault(name, value) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            (name, token.decode()),
        )


def get_secret(name: str) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT value FROM vault WHERE name=?", (name,)).fetchone()
    if row is None:
        return None
    try:
        return _fernet().decrypt(row["value"].encode()).decode()
    except InvalidToken:
        raise ValueError("vault key changed or value corrupt") from None


def list_secrets() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT name, updated_at FROM vault ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def delete_secret(name: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM vault WHERE name=?", (name,))
    return cur.rowcount > 0  # type: ignore[union-attr]
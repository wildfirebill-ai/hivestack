"""Identity — EC P-256 keypairs, one-time session-bound nonce challenges,
and signature verify (works for a verifier that never sees the private key)."""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..db import _conn


def issue(name: str) -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO economy_keys(name, public_pem, private_pem) VALUES (?,?,?)",
            (name, public_pem, private_pem),
        )
    return {"name": name, "public_key": public_pem}


def _private_key(name: str):
    with _conn() as con:
        row = con.execute("SELECT private_pem FROM economy_keys WHERE name=?", (name,)).fetchone()
    if row is None:
        raise LookupError(f"no identity for '{name}' — issue one first")
    return serialization.load_pem_private_key(row["private_pem"].encode(), password=None)


def public_key(name: str) -> str | None:
    with _conn() as con:
        row = con.execute("SELECT public_pem FROM economy_keys WHERE name=?", (name,)).fetchone()
    return row["public_pem"] if row else None  # type: ignore[index]


def issue_challenge(name: str) -> str:
    nonce = secrets.token_hex(24)
    with _conn() as con:
        con.execute("INSERT INTO economy_challenges(name, nonce) VALUES (?,?)", (name, nonce))
    return nonce


def sign(name: str, nonce: str) -> str:
    key = _private_key(name)
    digest = hashlib.sha256(nonce.encode()).digest()
    raw = key.sign(digest, ec.ECDSA(hashes.SHA256()))
    return base64.urlsafe_b64encode(raw).decode()


def verify(public_key_pem: str, nonce: str, signature_b64: str) -> tuple[bool, str]:
    try:
        pub = serialization.load_pem_public_key(public_key_pem.encode())
        raw = base64.urlsafe_b64decode(signature_b64.encode())
        digest = hashlib.sha256(nonce.encode()).digest()
        pub.verify(raw, digest, ec.ECDSA(hashes.SHA256()))
        return True, "signature valid"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def verify_session(name: str, nonce: str, signature_b64: str) -> tuple[bool, str]:
    """Verify a signature AND consume its one-time nonce (anti-replay)."""
    with _conn() as con:
        row = con.execute(
            "SELECT id, used FROM economy_challenges WHERE name=? AND nonce=? ORDER BY id DESC LIMIT 1",
            (name, nonce),
        ).fetchone()
    if row is None:
        return False, "unknown session nonce"
    pub = public_key(name)
    if pub is None:
        return False, "no identity for requester"
    ok, reason = verify(pub, nonce, signature_b64)
    if not ok:
        return False, reason
    if row["used"]:
        return False, "nonce already consumed (replay detected)"
    with _conn() as con:
        con.execute("UPDATE economy_challenges SET used=1 WHERE id=?", (row["id"],))
    return True, "signature valid (session opened)"
"""Federation — signed pings between hivestack nodes. An envelope is signed
with a local identity's key over its nonce; the peer atom-verified via
`ingest`. No on-chain components (experimental)."""

from __future__ import annotations

import datetime as _dt

import httpx

from ..config import settings
from . import identity


def peers() -> list[dict]:
    raw = settings.data.get("peers", {}) or {}
    return [{"name": n, "url": u} for n, u in raw.items()]


def _identity_name() -> str:
    return settings.data.get("economy", {}).get("node_identity") or "hivestack-node"


def ping(peer_name: str) -> dict:
    peer = next((p for p in peers() if p["name"] == peer_name), None)
    if peer is None:
        raise LookupError(f"peer '{peer_name}' not configured (add under peers: in config)")
    nonce = identity.issue_challenge(_identity_name())
    sig = identity.sign(_identity_name(), nonce)
    envelope = {
        "sender": _identity_name(),
        "public_key": identity.public_key(_identity_name()),
        "nonce": nonce,
        "signature": sig,
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "payload": {"msg": f"hello from hivestack at {_dt.datetime.now(_dt.timezone.utc):%H:%M:%S}"},
    }
    url = peer["url"].rstrip("/") + "/api/federation/ingest"
    try:
        r = httpx.post(url, json=envelope, timeout=15)
        r.raise_for_status()
        return {"peer": peer_name, "http": r.status_code, "response": r.json()}
    except httpx.HTTPError as exc:
        return {"peer": peer_name, "error": str(exc)}


def ingest(body: dict) -> dict:
    """Signature-verified inbound federation envelope (no bearer token)."""
    ok, reason = identity.verify_session(body.get("sender", ""), body.get("nonce", ""), body.get("signature", ""))
    if not ok:
        return {"ok": False, "error": reason}
    return {"ok": True, "responder": "hivestack", "from": body.get("sender"), "payload": body.get("payload")}
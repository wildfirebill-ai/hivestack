"""Economy, identity & federation — experimental, behind the economy module flag."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..economy import core, federation, identity

router = APIRouter(prefix="/api/economy", tags=["economy"])
_auth = Depends(security.require_token)


def _require_economy() -> None:
    if not settings.module_enabled("economy"):
        raise HTTPException(status_code=403, detail="economy module is disabled (experimental, opt-in)")


class AccountIn(BaseModel):
    name: str
    kind: str = "user"
    seed: float = 0.0


class GigIn(BaseModel):
    title: str
    reward: float
    owner: str


class PerformerIn(BaseModel):
    performer: str


class ApproverIn(BaseModel):
    approver: str


class NameIn(BaseModel):
    name: str


class SignIn(BaseModel):
    name: str
    nonce: str


class VerifyIn(BaseModel):
    nonce: str
    signature: str
    public_key: str | None = None
    name: str | None = None


class PeerIn(BaseModel):
    name: str
    url: str


@router.get("")
def overview(_: str = _auth) -> dict:
    _require_economy()
    return {"module": "economy", "accounts": len(core.accounts()),
            "open_gigs": len(core.gigs("open")), "ledger": len(core.ledger(10000))}


@router.get("/accounts")
def list_accounts(_: str = _auth) -> dict:
    _require_economy()
    return {"accounts": core.accounts()}


@router.post("/accounts")
def create_account(body: AccountIn, _: str = _auth) -> dict:
    _require_economy()
    return {"account": core.create_account(body.name, body.kind, body.seed)}


@router.get("/gigs")
def list_gigs(status: str | None = None, _: str = _auth) -> dict:
    _require_economy()
    return {"gigs": core.gigs(status)}


@router.post("/gigs")
def create_gig(body: GigIn, user: str = _auth) -> dict:
    _require_economy()
    gig_id = core.create_gig(body.title, body.reward, body.owner)
    from .. import governance

    governance.audit(user, "economy.gig.create", gig_id, {"title": body.title, "reward": body.reward})
    return {"gig_id": gig_id}


@router.post("/gigs/{gig_id}/claim")
def claim(body: PerformerIn, gig_id: str, _: str = _auth) -> dict:
    _require_economy()
    try:
        return {"gig": core.claim(gig_id, body.performer)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/gigs/{gig_id}/complete")
def complete(gig_id: str, user: str = _auth) -> dict:
    _require_economy()
    try:
        return {"gig": core.complete(gig_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/gigs/{gig_id}/settle")
def settle(body: ApproverIn, gig_id: str, user: str = _auth) -> dict:
    _require_economy()
    try:
        result = core.settle(gig_id, body.approver)
        from .. import governance

        governance.audit(user, "economy.gig.settle", gig_id, {"approved": True})
        return {"gig": result}
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/ledger")
def ledger(_: str = _auth) -> dict:
    _require_economy()
    return {"ledger": core.ledger()}


# ------------------------------------------------------------------ identity
@router.post("/identity/issue")
def issue_identity(body: NameIn, user: str = _auth) -> dict:
    _require_economy()
    ident = identity.issue(body.name)
    from .. import governance

    governance.audit(user, "economy.identity.issue", body.name, {"public_key": ident["public_key"][:60]})
    return ident


@router.post("/identity/challenge")
def challenge(body: NameIn, _: str = _auth) -> dict:
    _require_economy()
    return {"name": body.name, "nonce": identity.issue_challenge(body.name)}


@router.post("/identity/sign")
def sign(body: SignIn, _: str = _auth) -> dict:
    _require_economy()
    try:
        return {"name": body.name, "signature": identity.sign(body.name, body.nonce)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/identity/verify")
def verify(body: VerifyIn, _: str = _auth) -> dict:
    _require_economy()
    if body.public_key:
        ok, reason = identity.verify(body.public_key, body.nonce, body.signature)
    elif body.name:
        ok, reason = identity.verify_session(body.name, body.nonce, body.signature)
    else:
        raise HTTPException(status_code=422, detail="provide public_key or name")
    return {"ok": ok, "reason": reason}


# ------------------------------------------------------------------ federation
@router.get("/peers")
def list_peers(_: str = _auth) -> dict:
    _require_economy()
    return {"peers": federation.peers()}


@router.post("/peers")
def add_peer(body: PeerIn, user: str = _auth) -> dict:
    _require_economy()
    settings.data.setdefault("peers", {})[body.name] = body.url
    settings.save()
    from .. import governance

    governance.audit(user, "economy.peer.add", body.name, {"url": body.url})
    return {"peers": federation.peers()}


@router.post("/peers/{name}/ping")
def ping_peer(name: str, _: str = _auth) -> dict:
    _require_economy()
    try:
        return federation.ping(name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


# Public, signature-authenticated (no bearer token)
public_router = APIRouter(prefix="/api/federation", tags=["federation"])


@public_router.post("/ingest")
async def ingest(request: Request) -> dict:
    body = await request.json()
    return federation.ingest(body)
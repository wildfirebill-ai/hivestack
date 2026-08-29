"""Comms endpoints — channels (ingest/send/mailbox), encrypted vault, voice."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from .. import security
from ..channels import base as channels
from ..config import settings
from .. import vault as vault_mod
from .. import voice as voice_mod

router = APIRouter(prefix="/api", tags=["comms"])
_auth = Depends(security.require_token)


# ------------------------------------------------------------------ channels
class IngestIn(BaseModel):
    text: str
    from_id: str | None = None


class SendIn(BaseModel):
    text: str
    to: str | None = None


class MailIn(BaseModel):
    subject: str = ""
    body: str
    sender: str | None = None


@router.get("/channels")
def channels_list(_: str = _auth) -> dict:
    out = []
    for ch in settings.channels():
        tok_present = bool(os.getenv(ch.get("token_env") or ""))
        out.append({
            **ch,
            "token_present": tok_present,
            "offline_blocked": ch.get("platform") not in ("webhook", "email") and settings.offline_mode,
        })
    return {"channels": out, "offline_mode": settings.offline_mode}


@router.post("/channels/mail/ingest")
def mail_ingest(body: MailIn, _: str = _auth) -> dict:
    return channels.handle_email(body.subject, body.body, body.sender)


@router.post("/channels/{name}/ingest")
def channel_ingest(name: str, body: IngestIn, _: str = _auth) -> dict:
    cfg = settings.get_channel(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail="channel not found")
    if not cfg.get("enabled", True):
        raise HTTPException(status_code=403, detail="channel is disabled")
    return channels.handle_inbound(cfg, body.text, body.from_id)


@router.post("/channels/{name}/send")
def channel_send(name: str, body: SendIn, _: str = _auth) -> dict:
    cfg = settings.get_channel(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail="channel not found")
    try:
        return channels.send_to(cfg, body.text, body.to)
    except channels.ChannelError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.get("/channels/messages")
def channel_messages(_: str = _auth) -> dict:
    return {"messages": channels.mailbox()}


@router.post("/channels/{name}/enable")
def channel_enable(name: str, enabled: bool, _: str = _auth) -> dict:
    data = settings.data.setdefault("channels", {})
    if name not in data:
        raise HTTPException(status_code=404, detail="channel not found")
    data[name]["enabled"] = bool(enabled)
    settings.save()
    return {"name": name, "enabled": bool(enabled)}


# ------------------------------------------------------------------ vault
class SecretIn(BaseModel):
    name: str
    value: str


class GetIn(BaseModel):
    name: str


@router.get("/vault")
def vault_list(_: str = _auth) -> dict:
    return {"secrets": vault_mod.list_secrets()}


@router.post("/vault")
def vault_set(body: SecretIn, user: str = _auth) -> dict:
    vault_mod.set_secret(body.name, body.value)
    from .. import governance

    governance.audit(user, "vault.set", body.name, {})
    return {"name": body.name, "stored": True}


@router.post("/vault/get")
def vault_get(body: GetIn, _: str = _auth) -> dict:
    value = vault_mod.get_secret(body.name)
    if value is None:
        raise HTTPException(status_code=404, detail="secret not found")
    return {"name": body.name, "value": value}


@router.delete("/vault/{name}")
def vault_delete(name: str, _: str = _auth) -> dict:
    if not vault_mod.delete_secret(name):
        raise HTTPException(status_code=404, detail="secret not found")
    return {"removed": name}


# ------------------------------------------------------------------ voice
class SpeakIn(BaseModel):
    text: str


class ActivateIn(BaseModel):
    transcript: str | None = None


@router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile, _: str = _auth) -> dict:
    if not settings.module_enabled("voice"):
        raise HTTPException(status_code=403, detail="voice module is disabled")
    data = await file.read()
    try:
        return voice_mod.transcribe(data)
    except voice_mod.VoiceUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None


@router.post("/voice/speak")
def voice_speak(body: SpeakIn, _: str = _auth) -> dict:
    if not settings.module_enabled("voice"):
        raise HTTPException(status_code=403, detail="voice module is disabled")
    try:
        return voice_mod.speak(body.text)
    except voice_mod.VoiceUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None


@router.post("/voice/activate")
def voice_activate(body: ActivateIn, _: str = _auth) -> dict:
    if not settings.module_enabled("voice"):
        raise HTTPException(status_code=403, detail="voice module is disabled")
    try:
        return voice_mod.activate(body.transcript)
    except voice_mod.VoiceUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None
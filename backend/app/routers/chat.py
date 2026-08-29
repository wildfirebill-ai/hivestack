"""Chat — real model inference behind the provider gate, plus SSE streaming.

provider "fallback" aliases the deterministic CPU responder from Stage 1
(kept for offline demos / no-model bootstrapping)."""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import security
from ..config import settings
from ..db import _conn
from ..fallback import fallback
from ..inference import InferenceError, run_chat, stream_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])
_auth = Depends(security.require_token)


class ChatIn(BaseModel):
    message: str
    provider: str | None = None
    model: str | None = None
    system: str | None = None
    prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    rag: bool = False  # retrieve from memory and inject as context


def _system_text(body: ChatIn) -> str:
    if body.system is not None:
        return body.system
    if body.prompt:
        return settings.get_prompt(body.prompt) or ""
    return settings.get_prompt("default") or ""


def _rag_context(message: str, system: str) -> tuple[str, int]:
    """Returns (augmented_system, num_context_lines). No-ops when memory is off."""
    if not settings.module_enabled("memory"):
        return system, 0
    try:
        from ..memory import context as _ctx

        info = _ctx.retrieve_context(message, k=4)
    except Exception:  # noqa: BLE001
        return system, 0
    if not info["lines"]:
        return system, 0
    block = "\nRelevant memory context:\n" + "\n".join(info["lines"])
    return system + block, len(info["lines"])


def _record(
    role: str,
    content: str,
    provider: str | None,
    model: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO messages(role, content, source, provider, model, input_tokens, output_tokens)"
            " VALUES (?,?,?,?,?,?,?)",
            (role, content, provider or "", provider or "", model or "", input_tokens, output_tokens),
        )


def _validate(body: ChatIn) -> str:
    if not settings.module_enabled("chat"):
        raise HTTPException(status_code=403, detail="chat module is disabled")
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is empty")
    return message


@router.post("")
def chat(body: ChatIn, _: str = _auth) -> dict:
    message = _validate(body)

    if (body.provider or "").lower() == "fallback":
        _record("user", message, "fallback", None)
        reply = fallback.respond(message)
        _record("assistant", reply, "fallback", None)
        return {"reply": reply, "model": None, "provider": "fallback", "source": "fallback",
                "usage": {"input_tokens": 0, "output_tokens": 0}}

    _record("user", message, body.provider, body.model)
    system = _system_text(body)
    if body.rag:
        system, rag_lines = _rag_context(message, system)
    else:
        rag_lines = 0
    try:
        result, entry = run_chat(
            user=message,
            provider=body.provider,
            model=body.model,
            system=system,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except InferenceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None

    usage = result["usage"]
    _record("assistant", result["content"], entry["provider"], entry["name"], usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    return {
        "reply": result["content"],
        "model": entry["name"],
        "provider": entry["provider"],
        "usage": usage,
        "rag_contexts": rag_lines if body.rag else 0,
    }


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@router.post("/stream")
async def chat_stream(body: ChatIn, _: str = _auth) -> StreamingResponse:
    message = _validate(body)

    def gen() -> Iterator[str]:
        try:
            if (body.provider or "").lower() == "fallback":
                reply = fallback.respond(message)
                _record("user", message, "fallback", None)
                yield _sse({"delta": reply})
                yield _sse({"done": True, "model": None, "provider": "fallback", "usage": {"input_tokens": 0, "output_tokens": 0}})
                _record("assistant", reply, "fallback", None)
                return

            stream, entry = stream_chat(
                user=message,
                provider=body.provider,
                model=body.model,
                system=_system_text(body),
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
            parts: list[str] = []
            usage: dict = {}
            _record("user", message, entry["provider"], entry["name"])
            for evt in stream:
                if "delta" in evt:
                    parts.append(evt["delta"])
                    yield _sse({"delta": evt["delta"]})
                elif evt.get("done"):
                    usage = evt.get("usage", {})
                    break
            yield _sse({
                "done": True,
                "model": entry["name"],
                "provider": entry["provider"],
                "usage": usage,
            })
            _record(
                "assistant",
                "".join(parts),
                entry["provider"],
                entry["name"],
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        except InferenceError as exc:
            yield _sse({"error": str(exc)})
            yield _sse({"done": True})

    return StreamingResponse(gen(), media_type="text/event-stream")
"""Communication channels — inbound dispatch + reply pipeline, outbound
provider connectors (gated by offline mode), and a mailbox audit log.

The reply pipeline tries, in order: (1) a memory-injected agent run, (2) a
single RAG-augmented completion, (3) an offline CPU-fallback reply enriched
with the top memory matches — so messages always get a memory-backed answer
even with no model attached."""

from __future__ import annotations

import os

import httpx

from ..config import settings
from ..db import _conn
from ..fallback import fallback


class ChannelError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def mailbox(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, channel, direction, from_id, text, reply, created_at"
            " FROM channel_messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def _record(channel: str, direction: str, from_id: str | None, text: str | None, reply: str | None) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO channel_messages(channel, direction, from_id, text, reply) VALUES (?,?,?,?,?)",
            (channel, direction, from_id, text, reply),
        )


def _memory_hint(text: str, k: int = 3) -> list[str]:
    if not settings.module_enabled("memory"):
        return []
    try:
        from ..memory import context as _ctx

        return _ctx.retrieve_context(text, k=k)["lines"]
    except Exception:  # noqa: BLE001
        return []


def reply_to(text: str, from_id: str | None = None, scope: str = "global") -> dict:
    """Best-effort reply: agent w/ memory → RAG chat → offline memory fallback."""
    clean = (text or "").strip()
    if not clean:
        clean = "hello"

    # 1) memory-injected agent run
    try:
        from ..agents import runtime

        rid = runtime.create(
            goal=f"Reply to this user message. Message: {clean}",
            provider=None, model=None,
            max_steps=6, allowed_scopes=["low", "medium"], memory=True,
        )
        runtime.start(rid)
        for _ in range(240):
            s = runtime.task_summary(rid)
            if s and s["status"] in ("completed", "error", "cancelled"):
                break
            import time

            time.sleep(0.25)
        detail = runtime.task_detail(rid)
        if detail and detail["status"] == "completed":
            answer = ""
            for ev in detail.get("events", []):
                if ev["kind"] == "completed":
                    import json

                    try:
                        answer = (json.loads(ev["data"]) or {}).get("answer", "") or ""
                    except json.JSONDecodeError:
                        pass
            if answer:
                return {"reply": answer, "source": "agent", "run": rid}
    except Exception:  # noqa: BLE001
        pass

    # 2) single RAG-augmented completion
    try:
        from ..inference.client import run_chat

        system = "You are hivestack, replying to a chat/signal message. Be concise."
        hints = _memory_hint(clean)
        if hints:
            system += "\n\nRelevant memory context:\n" + "\n".join(hints)
        result, _entry = run_chat(user=clean, system=system, max_tokens=300)
        if result.get("content", "").strip():
            return {"reply": result["content"], "source": "chat-rag"}
    except Exception:  # noqa: BLE001
        pass

    # 3) offline memory-backed fallback
    reply = fallback.respond(clean)
    hints = _memory_hint(clean)
    if hints:
        reply += "\n\n(since a model is offline, here's what memory recalls)\n" + "\n".join(hints[:3])
    return {"reply": reply, "source": "fallback"}


def handle_inbound(channel_cfg: dict, text: str, from_id: str | None = None) -> dict:
    trigger = (channel_cfg.get("trigger_workflow") or "").strip()
    if trigger:
        try:
            from ..workflows import engine as _wfe

            wid = _wfe.get_workflow(trigger)
            if wid is not None:
                run_id = _wfe.start_run(wid["id"])
                result = {"reply": f"workflow '{trigger}' started ({run_id})", "source": "workflow", "run": run_id}
                _record(channel_cfg["name"], "inbound", from_id, text, result["reply"])
                return result
        except Exception:  # noqa: BLE001
            pass
    result = reply_to(text, from_id)
    _record(channel_cfg["name"], "inbound", from_id, text, result["reply"])
    return result


def handle_email(subject: str, body: str, sender: str | None = None) -> dict:
    mail_cfg = settings.get_channel("mail") or {"name": "mail", "platform": "email", "enabled": True}
    text = f"{subject}\n\n{body}" if subject else body
    result = handle_inbound({**mail_cfg, "name": "mail"}, text, sender)
    result["subject"] = subject
    return result


# ------------------------------------------------------------------ outbound
def _token(cfg: dict) -> str:
    env = cfg.get("token_env") or ""
    tok = os.getenv(env) or ""
    if not tok:
        raise ChannelError(f"token missing (env {env or '?'}) — configure the channel", 400)
    return tok


def send_to(channel_cfg: dict, text: str, to: str | None = None) -> dict:
    """Outbound send. External platforms are refused while offline (403)."""
    platform = channel_cfg.get("platform", "webhook")
    name = channel_cfg.get("name", "?")
    if not channel_cfg.get("enabled", True):
        raise ChannelError(f"channel '{name}' is disabled", 403)
    if platform == "webhook":
        _record(name, "outbound", to, text, None)
        return {"ok": True, "channel": name, "platform": "webhook", "to": to, "text": text[:40]}
    if settings.offline_mode:
        raise ChannelError(f"channel '{name}' ({platform}) is an outside provider — offline mode is on", 403)

    payload = None
    url = None
    headers = {"Content-Type": "application/json"}
    if platform == "telegram":
        tok = _token(channel_cfg)
        assert to, "telegram needs a chat_id"
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        payload = {"chat_id": str(to), "text": text}
    elif platform == "discord":
        url = channel_cfg.get("webhook_url")
        if not url:
            raise ChannelError("discord channel needs webhook_url", 400)
        payload = {"content": text}
    elif platform == "slack":
        url = channel_cfg.get("webhook_url")
        if not url:
            raise ChannelError("slack channel needs webhook_url", 400)
        payload = {"text": text}
    elif platform == "matrix":
        tok = _token(channel_cfg)
        room = channel_cfg.get("room") or (to or "")
        assert room, "matrix needs a room id"
        url = f"https://matrix-client.example.org/_matrix/client/v3/rooms/{room}/send/m.room.message"
        headers["Authorization"] = f"Bearer {tok}"
        payload = {"msgtype": "m.text", "body": text}
    else:
        raise ChannelError(f"unknown platform '{platform}'", 400)

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        _record(name, "outbound", to, text, f"http {r.status_code}")
        return {"ok": True, "channel": name, "platform": platform, "to": to, "http": r.status_code}
    except httpx.HTTPError as exc:
        raise ChannelError(f"send to '{name}' failed: {exc}", 502) from None
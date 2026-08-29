"""Agent runtime — a bounded plan→act→verify loop over the provider gate.

A run is a row in `tasks` + `run_events`. The executor thread performs LLM turns
via inference.complete (which manages history itself), parses a single tool call
per turn, executes it through the policy-gated tool registry, and stops at a
plain-text final answer or the step cap. Every action is audited as an event.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any

from ..config import settings
from ..db import _conn
from ..inference.base import InferenceError as _IE
from ..inference.client import complete
from .tools import execute_tool, policy_denial, prompt_for_tools, registry

_cancel: dict[str, bool] = {}
_run_lock = threading.Lock()


SYSTEM_BASE = (
    "You are the hivestack agent executor, running locally on the user's own hardware.\n"
    "You receive a goal and a conversation. To accomplish it you may call ONE tool per turn.\n"
    "When you need a tool, reply with ONLY a JSON fenced block like this:\n"
    "```json\n{{\"tool\": \"tool_name\", \"args\": {{...}}}}\n```\n"
    "After a tool result, continue: call another tool or give the final answer as plain text.\n"
    "If a tool is denied or errors, adapt, or answer with what you could determine.\n"
    "Keep final answers concise.\n\n"
    "Available tools:\n{tools}"
)


# ------------------------------------------------------------------ persistence
def _row(run_id: str) -> dict | None:
    with _conn() as con:
        r = con.execute("SELECT * FROM tasks WHERE id=?", (run_id,)).fetchone()
    return dict(r) if r else None


def events(run_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
    return [dict(r) for r in rows]


def _event(run_id: str, kind: str, data: dict) -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO run_events(run_id, seq, kind, data) VALUES (?,?,?,?)",
            (run_id, time.time_ns(), kind, json.dumps(data)),
        )
        con.execute("UPDATE tasks SET updated_at=datetime('now') WHERE id=?", (run_id,))


def _update(run_id: str, **fields: Any) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE tasks SET {cols} WHERE id=?", (*fields.values(), run_id))


def create(
    *,
    goal: str,
    name: str = "",
    provider: str | None = None,
    model: str | None = None,
    max_steps: int = 10,
    allowed_scopes: list[str] | None = None,
    auto: str = "auto",
    memory: bool = False,
    skill: str | None = None,
) -> str:
    run_id = uuid.uuid4().hex[:12]
    scopes = allowed_scopes or ["low"]  # conservative default: harmless tools only
    with _conn() as con:
        con.execute(
            "INSERT INTO tasks(id,name,goal,provider,model,status,max_steps,allowed_scopes,policy)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, name, goal, provider, model, "queued", int(max_steps), json.dumps(scopes),
             json.dumps({"allowed_scopes": scopes, "auto": auto, "memory": memory, "skill": skill})),
        )
    return run_id


def cancel(run_id: str) -> None:
    _cancel[run_id] = True


# ------------------------------------------------------------------ parsing
def parse_tool_call(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("{") and '"tool"' in t:
        try:
            obj = json.loads(t)
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    m = re.search(r"```json\s*\n?(\{.*?\})\s*```", t, re.S)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    return None


# ------------------------------------------------------------------ executor
def run_task(run_id: str) -> None:
    run = _row(run_id)
    if run is None:
        return
    _update(run_id, status="running")
    _cancel.pop(run_id, None)
    policy = json.loads(run["policy"] or "{}")
    provider, model = run.get("provider"), run.get("model")
    goal = run["goal"]
    tools = registry.all()

    _event(run_id, "started", {"goal": goal, "provider": provider, "model": model, "policy": policy})

    try:
        from ..governance import allow_new_run

        ok, reason = allow_new_run()
        if not ok:
            _update(run_id, status="budget_capped")
            _event(run_id, "budget_capped", {"reason": reason})
            return
    except Exception:  # noqa: BLE001
        pass

    system = SYSTEM_BASE.format(tools=prompt_for_tools(tools))

    skill_name = policy.get("skill")
    if skill_name and settings.module_enabled("skills"):
        try:
            from ..skills.store import get_skill as _get_skill

            skill = _get_skill(skill_name)
            if skill and skill.get("status") == "active":
                _event(run_id, "skill", {"name": skill_name})
                system = (skill.get("instructions") or "") + "\n\n" + system
        except Exception:  # noqa: BLE001
            pass

    if policy.get("memory") and settings.module_enabled("memory"):
        try:
            from ..memory import context as _ctx

            info = _ctx.retrieve_context(goal, k=4)
            if info["lines"]:
                system += "\n\nRelevant memory context:\n" + "\n".join(info["lines"])
        except Exception:  # noqa: BLE001
            pass

    messages: list[dict] = [{"role": "user", "content": goal}]
    total_in = total_out = 0
    max_steps = min(int(run.get("max_steps") or 10), 40)

    for step in range(1, max_steps + 1):
        if _cancel.get(run_id):
            _update(run_id, status="cancelled")
            _event(run_id, "cancelled", {"step": step})
            return
        try:
            result, entry = complete(
                provider=provider,
                model=model,
                system=system,
                messages=messages,
                max_tokens=512,
            )
        except _IE as exc:
            _update(run_id, status="error", error=str(exc))
            _event(run_id, "error", {"message": str(exc)})
            return
        usage = result.get("usage") or {}
        total_in += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)
        try:
            from ..governance import within_per_run

            ok, reason = within_per_run(total_in + total_out)
            if not ok:
                _update(run_id, status="budget_capped", tokens_in=total_in, tokens_out=total_out)
                _event(run_id, "budget_capped", {"reason": reason, "step": step})
                return
        except Exception:  # noqa: BLE001
            pass
        content = (result.get("content") or "").strip()

        messages.append({"role": "assistant", "content": content})
        _event(run_id, "llm", {"step": step, "content": content[:600]})

        call = parse_tool_call(content)
        if call is None:
            _update(run_id, status="completed", tokens_in=total_in, tokens_out=total_out)
            _event(run_id, "completed", {"step": step, "answer": content[:1000]})
            return

        tool = registry.get(str(call.get("tool", "")))
        args = call.get("args") or {}
        if tool is None:
            note = f"unknown tool '{call.get('tool')}'"
            _event(run_id, "tool_error", {"step": step, "tool": call.get("tool"), "message": note})
            messages.append({"role": "user", "content": f"[tool] {note}"})
            continue

        denial = policy_denial(tool, policy)
        if denial:
            _event(run_id, "tool_denied", {"step": step, "tool": tool.name, "reason": denial})
            messages.append({"role": "user", "content": f"[tool {tool.name}] DENIED: {denial}"})
            continue

        _event(run_id, "tool_call", {"step": step, "tool": tool.name, "args": args})
        output, err = execute_tool(tool, args, policy)
        _event(run_id, "tool_result", {"step": step, "tool": tool.name, "out": output[:600], "err": err})
        messages.append({"role": "user", "content": f"[tool {tool.name}] result: {output}"})

    _update(run_id, status="completed", tokens_in=total_in, tokens_out=total_out)
    _event(run_id, "completed", {"step": "max", "note": "step limit reached"})


def start(run_id: str) -> None:
    threading.Thread(target=run_task, args=(run_id,), daemon=True, name=f"agent-{run_id}").start()


# ------------------------------------------------------------------ serialization
def task_summary(run_id: str) -> dict | None:
    run = _row(run_id)
    if run is None:
        return None
    return {"id": run["id"], "name": run["name"], "goal": run["goal"], "status": run["status"],
            "provider": run["provider"], "model": run["model"], "max_steps": run["max_steps"],
            "allowed_scopes": json.loads(run["allowed_scopes"] or "[]"),
            "tokens_in": run["tokens_in"], "tokens_out": run["tokens_out"],
            "error": run.get("error"), "created_at": run["created_at"],
            "updated_at": run["updated_at"]}


def task_detail(run_id: str) -> dict | None:
    summary = task_summary(run_id)
    if summary is None:
        return None
    summary["events"] = events(run_id)
    return summary
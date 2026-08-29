"""Workflow engine — execute a persisted DAG of steps with parallel fan-out,
per-step retries, checkpoints (every step result persisted), approval stops,
and resume/cancel. Step types: tool, agent (runs an agent task), chat
(single completion), wait, map (parallel agent/tool/chat fan-out), board
(emit a kanban card)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor as _Pool
from typing import Any

from ..config import settings
from ..db import _conn
from . import boards as _boards

_cancel: dict[str, bool] = {}
_approval: dict[str, threading.Event] = {}
_state_lock = threading.RLock()


# ------------------------------------------------------------------ db helpers
def _row(sql: str, params: tuple = ()) -> dict | None:
    with _conn() as con:
        r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def _update_run(run_id: str, **fields: Any) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(f"UPDATE workflow_runs SET {cols}, updated_at=datetime('now') WHERE id=?", (*fields.values(), run_id))


def _set_run_status(run_id: str, status: str, error: str | None = None) -> None:
    d: dict[str, Any] = {"status": status}
    if error is not None:
        d["error"] = error
    _update_run(run_id, **d)


def _step_row(run_id: str, step_id: str) -> dict | None:
    return _row("SELECT * FROM workflow_step_runs WHERE run_id=? AND step_id=?", (run_id, step_id))


def _upsert_step(
    run_id: str,
    step_id: str,
    status: str | None,
    output: dict | None = None,
    attempts: int | None = None,
    start: bool = False,
    finish: bool = False,
) -> None:
    row = _step_row(run_id, step_id)
    with _conn() as con:
        if row is None:
            con.execute(
                "INSERT INTO workflow_step_runs(run_id, step_id, status, attempts, output, started_at)"
                " VALUES (?,?,?,?,?,datetime('now'))",
                (run_id, step_id, status or "pending", attempts or 1, json.dumps(output) if output else None),
            )
            return
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status=?")
            params.append(status)
        if output is not None:
            sets.append("output=?")
            params.append(json.dumps(output))
        if attempts is not None:
            sets.append("attempts=?")
            params.append(attempts)
        if start:
            sets.append("started_at=datetime('now')")
        if finish:
            sets.append("finished_at=datetime('now')")
        if not sets:
            return
        params += [run_id, step_id]
        con.execute(f"UPDATE workflow_step_runs SET {', '.join(sets)} WHERE run_id=? AND step_id=?", params)


def _ctx(run_id: str) -> dict:
    run = _row("SELECT context FROM workflow_runs WHERE id=?", (run_id,))
    if not run or not run.get("context"):
        return {}
    try:
        return json.loads(run["context"])
    except json.JSONDecodeError:
        return {}


def _save_ctx(run_id: str, ctx: dict) -> None:
    _update_run(run_id, context=json.dumps(ctx))


# ------------------------------------------------------------------ creation
def create_workflow(name: str, definition: dict) -> str:
    wid = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute("INSERT INTO workflows(id, name, definition) VALUES (?,?,?)", (wid, name, json.dumps(definition)))
    return wid


def get_workflow(wid: str) -> dict | None:
    row = _row("SELECT * FROM workflows WHERE id=?", (wid,))
    if not row:
        return None
    row["definition"] = json.loads(row["definition"])
    return row


def list_workflows() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT id,name,enabled,created_at FROM workflows ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_workflow(wid: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM workflows WHERE id=?", (wid,))
    return cur.rowcount > 0


def start_run(wid: str) -> str:
    wf = get_workflow(wid)
    if wf is None:
        raise LookupError(f"workflow '{wid}' not found")
    run_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO workflow_runs(id, workflow_id, status, context) VALUES (?,?,?,?)",
            (run_id, wid, "queued", "{}"),
        )
    _cancel.pop(run_id, None)
    threading.Thread(target=_execute, args=(run_id, wf["definition"], False), daemon=True).start()
    return run_id


def _step_ids(definition: dict) -> list[str]:
    return [s.get("id", "") for s in definition.get("steps", [])]


# ------------------------------------------------------------------ execution
def _sub(text: Any, ctx: dict, item: Any = None) -> str:
    s = str(text)
    for k, v in ctx.items():
        s = s.replace("{" + k + "}", str(v))
    if item is not None:
        s = s.replace("{item}", str(item))
    return s


def _sub_args(d: dict, ctx: dict, item: Any = None) -> dict:
    out = {}
    for k, v in d.items():
        out[k] = _sub(v, ctx, item) if isinstance(v, str) else v
    return out


def _agent_sync(goal: str, step: dict) -> dict:
    from ..agents import runtime as _ar

    rid = _ar.create(
        goal=goal,
        provider=step.get("provider"),
        model=step.get("model"),
        max_steps=int(step.get("max_steps", 8)),
        allowed_scopes=step.get("allowed_scopes"),
    )
    _ar.start(rid)
    for _ in range(1200):  # ~10 min cap
        s = _ar.task_summary(rid)
        if s and s["status"] in ("completed", "error", "cancelled"):
            break
        time.sleep(0.5)
    detail = _ar.task_detail(rid)
    answer = ""
    status = detail.get("status") if detail else "unknown"
    if detail:
        for ev in detail.get("events", []):
            if ev["kind"] == "completed":
                try:
                    answer = (json.loads(ev["data"]) or {}).get("answer", "") or ""
                except json.JSONDecodeError:
                    answer = ""
    return {"answer": answer, "status": status, "task_id": rid}


def _run_one(step: dict, ctx: dict, item: Any = None) -> dict:
    """Run a single step (with {item} substitution when set). Returns
    {"ok": bool, "output": str, "error": str|None}."""
    t = step.get("type")
    try:
        if t == "tool":
            from ..agents.tools import execute_tool, registry as _treg

            tool = _treg.get(step.get("tool", ""))
            if tool is None:
                raise ValueError(f"unknown tool '{step.get('tool')}'")
            args = _sub_args(step.get("args") or {}, ctx, item)
            policy = {"allowed_scopes": step.get("allowed_scopes") or ["low", "medium", "high"], "auto": "auto"}
            out, err = execute_tool(tool, args, policy)
            if err:
                raise ValueError(out)
            return {"ok": True, "output": out}
        if t == "agent":
            goal = _sub(step.get("goal", ""), ctx, item)
            out = _agent_sync(goal, step)
            if out["status"] == "error" and not out["answer"]:
                return {"ok": True, "output": f"task {out['task_id']} errored (see agent runs)"}
            return {"ok": True, "output": out["answer"] or f"agent {out['task_id']} → {out['status']}"}
        if t == "chat":
            from ..inference.client import complete

            prompt = _sub(step.get("prompt", ""), ctx, item)
            res, _entry = complete(system=step.get("system", ""), messages=[{"role": "user", "content": prompt}],
                                   provider=step.get("provider"), model=step.get("model"))
            return {"ok": True, "output": res["content"]}
        if t == "wait":
            secs = min(int(step.get("seconds", 1)), 300)
            deadline = time.time() + secs
            while time.time() < deadline:
                time.sleep(0.3)
            return {"ok": True, "output": f"waited {secs}s"}
        if t == "map":
            items = step.get("items") or []
            inner = step.get("inner") or {}
            results = []
            for it in items:
                r = _run_one(inner, ctx, item=it)
                results.append({"item": it, "ok": r["ok"], "output": r["output"]})
            return {"ok": True, "output": json.dumps(results)}
        if t == "board":
            card_id = _boards.add_card(
                board_id=_sub(step.get("board", ""), ctx, item),
                column=_sub(step.get("column", "Todo"), ctx, item),
                title=_sub(step.get("title", "workflow card"), ctx, item),
                body=_sub(step.get("body", ""), ctx, item),
            )
            return {"ok": True, "output": f"card {card_id}"}
        raise ValueError(f"unknown step type '{t}'")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc), "error": str(exc)}


def _execute(run_id: str, definition: dict, resume: bool) -> None:
    try:
        _execute_loop(run_id, definition, resume)
    except Exception as exc:  # noqa: BLE001
        _set_run_status(run_id, "failed", error=str(exc))
    finally:
        _approval.pop(run_id, None)


def _execute_loop(run_id: str, definition: dict, resume: bool) -> None:
    steps = definition.get("steps", [])
    ids = [s.get("id", "") for s in steps]
    if not ids:
        _set_run_status(run_id, "completed")
        return

    # load checkpoints
    completed: set[str] = set()
    ctx: dict = {}
    with _conn() as con:
        rows = con.execute("SELECT step_id, status, output FROM workflow_step_runs WHERE run_id=?", (run_id,)).fetchall()
    for r in rows:
        if r["status"] == "success":
            completed.add(r["step_id"])
            if r["output"]:
                try:
                    ctx[r["step_id"]] = (json.loads(r["output"]) or {}).get("output", "")
                except json.JSONDecodeError:
                    pass
        elif resume and r["status"] in ("failed", "awaiting_approval", "pending"):
            with _conn() as con:
                con.execute("UPDATE workflow_step_runs SET status='pending', output=NULL WHERE run_id=? AND step_id=?", (run_id, r["step_id"]))
    _save_ctx(run_id, ctx)
    _set_run_status(run_id, "running")
    ctx_lock = threading.RLock()

    def _persist(step: dict, result: dict, attempts: int) -> None:
        _upsert_step(run_id, step.get("id", ""), "success" if result["ok"] else "failed",
                     output=result, attempts=attempts, finish=True)

    def _execute_step(step: dict) -> dict:
        sid = step["id"]
        attempts = 0
        retry = int(step.get("retry", 0))
        while True:
            attempts += 1
            result = _run_one(step, ctx)
            if result["ok"] or attempts > retry:
                with ctx_lock:
                    ctx[sid] = result.get("output", "")
                    _save_ctx(run_id, ctx)
                _persist(step, result, attempts)
                return result
            time.sleep(1.0 * attempts)

    while True:
        if _cancel.get(run_id):
            _set_run_status(run_id, "cancelled")
            return
        ready = [
            s for s in steps
            if s.get("id", "") not in completed
            and all(d in completed for d in s.get("deps", []))
        ]
        if not ready:
            done_ok = len(completed) == len(ids)
            _set_run_status(run_id, "completed" if done_ok else "failed",
                            error=None if done_ok else "unresolvable dependency graph")
            return
        # approval stops gate the wave
        approval = [s for s in ready if s.get("mode") == "approval"]
        auto = [s for s in ready if s.get("mode") != "approval"]
        if auto:
            with _Pool(max_workers=min(len(auto), 8)) as pool:
                futures = {pool.submit(_execute_step, s): s for s in auto}
                for fut, s in futures.items():
                    completed.add(s["id"])
                    if not s.get("continue_on_error", False):
                        result = fut.result()
                        if not result["ok"]:
                            _set_run_status(run_id, "failed", error=result.get("error", result.get("output", "")))
                            return
        for s in approval:
            sid = s["id"]
            _upsert_step(run_id, sid, "awaiting_approval", output={"note": s.get("note", "needs approval")}, attempts=1, start=True)
            _update_run(run_id, status="awaiting_approval", current_step=sid)
            evt = _approval.setdefault(run_id, threading.Event())
            # wait for approve/deny (or cancel), polling so cancel still works
            decided = False
            while not decided:
                if _cancel.get(run_id):
                    _set_run_status(run_id, "cancelled")
                    return
                if evt.wait(0.5):
                    decided = True
            row = _step_row(run_id, sid)
            decision = None
            if row and row["output"]:
                try:
                    decision = (json.loads(row["output"]) or {}).get("decision")
                except json.JSONDecodeError:
                    pass
            if decision is True:
                result = _execute_step(s)
                if not result["ok"]:
                    _set_run_status(run_id, "failed", error=str(result.get("error", result.get("output", ""))))
                    return
            else:
                _upsert_step(run_id, sid, "skipped", output={"note": "approval denied"}, finish=True)
            completed.add(sid)
            _update_run(run_id, status="running")
            _save_ctx(run_id, ctx)


def run_detail(run_id: str) -> dict | None:
    run = _row("SELECT * FROM workflow_runs WHERE id=?", (run_id,))
    if run is None:
        return None
    with _conn() as con:
        rows = con.execute("SELECT * FROM workflow_step_runs WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
    run["steps"] = [dict(r) for r in rows]
    if run["context"]:
        try:
            run["context"] = json.loads(run["context"])
        except json.JSONDecodeError:
            pass
    return run


def approve(run_id: str, approve: bool, note: str = "") -> dict:
    run = _row("SELECT status, current_step FROM workflow_runs WHERE id=?", (run_id,))
    if run is None:
        raise LookupError("run not found")
    step_id = run.get("current_step")
    if not step_id:
        raise ValueError("run is not awaiting approval")
    _upsert_step(run_id, step_id, None, output={"decision": approve, "note": note})  # keep status, only patch output
    if approve:
        _update_run(run_id, status="running")
    _approval.get(run_id, threading.Event()).set()
    return {"run_id": run_id, "approved": approve}


def resume(run_id: str) -> dict:
    run = _row("SELECT workflow_id FROM workflow_runs WHERE id=?", (run_id,))
    if run is None:
        raise LookupError("run not found")
    wf = get_workflow(run["workflow_id"])
    _cancel.pop(run_id, None)
    threading.Thread(target=_execute, args=(run_id, wf["definition"], True), daemon=True).start()
    return {"run_id": run_id}


def cancel(run_id: str) -> None:
    _cancel[run_id] = True
    _approval.get(run_id, threading.Event()).set()


def list_runs() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, workflow_id, status, current_step, error, created_at, updated_at"
            " FROM workflow_runs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]
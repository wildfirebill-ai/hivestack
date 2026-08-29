"""Workflow scheduling — cron and interval schedules, run in a daemon thread."""

from __future__ import annotations

import datetime as _dt
import threading
import time
import uuid

from croniter import croniter

from ..db import _conn
from . import engine

_stop = threading.Event()
_thread: threading.Thread | None = None


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _iso(dt: _dt.datetime) -> str:
    return dt.isoformat()


def _next(kind: str, value: str, base: _dt.datetime) -> str | None:
    try:
        if kind == "cron":
            return _iso(croniter(value, base).get_next(_dt.datetime))
        if kind == "interval":
            return _iso(base + _dt.timedelta(seconds=max(int(value), 5)))
    except (ValueError, KeyError, TypeError):
        return None
    return None


def list_schedules() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM schedules ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def create_schedule(workflow_id: str, kind: str, value: str, enabled: bool = True) -> dict:
    if engine.get_workflow(workflow_id) is None:
        raise LookupError("workflow not found")
    if kind not in ("cron", "interval"):
        raise ValueError("kind must be cron or interval")
    sid = uuid.uuid4().hex[:12]
    nxt = _next(kind, value, _now())
    with _conn() as con:
        con.execute(
            "INSERT INTO schedules(id, workflow_id, kind, value, enabled, next_run_at) VALUES (?,?,?,?,?,?)",
            (sid, workflow_id, kind, value, int(enabled), nxt),
        )
    return {"id": sid, "workflow_id": workflow_id, "kind": kind, "value": value, "enabled": bool(enabled), "next_run_at": nxt}


def delete_schedule(schedule_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    return cur.rowcount > 0


def toggle_schedule(schedule_id: str, enabled: bool) -> dict | None:
    with _conn() as con:
        cur = con.execute("UPDATE schedules SET enabled=? WHERE id=?", (int(enabled), schedule_id))
        if cur.rowcount == 0:
            return None
    rows = [s for s in list_schedules() if s["id"] == schedule_id]
    return rows[0] if rows else None


def _tick() -> None:
    now = _now()
    for sched in list_schedules():
        if not sched["enabled"]:
            continue
        nxt = sched["next_run_at"]
        due = nxt is not None and nxt <= _iso(now)
        if not due:
            continue
        try:
            engine.start_run(sched["workflow_id"])
        except Exception:  # noqa: BLE001
            pass
        recompute = _next(sched["kind"], sched["value"], now)
        with _conn() as con:
            con.execute("UPDATE schedules SET next_run_at=? WHERE id=?", (recompute, sched["id"]))


def _loop() -> None:
    while not _stop.is_set():
        try:
            _tick()
        except Exception:  # noqa: BLE001
            pass
        _stop.wait(20)


def start() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_loop, daemon=True, name="hivestack-scheduler")
        _thread.start()


def stop() -> None:
    _stop.set()
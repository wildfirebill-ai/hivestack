"""Chaos experiments — demo targets whose telemetry can be fault-injected from
a background thread, simulating real incidents for the AIOps loop."""

from __future__ import annotations

import random
import threading
import time
import uuid

from ..db import _conn
from ..config import settings
from . import core

DEMO_TARGETS = {
    "web-api": {"label": "Web API service", "metric": "web_api.latency_ms", "baseline": 8,
                "faults": {"latency": 40, "down": 200}},
    "db": {"label": "Database", "metric": "db.query_ms", "baseline": 4,
           "faults": {"latency": 60, "down": 500}},
    "worker": {"label": "Background worker", "metric": "worker.cpu", "baseline": 12,
               "faults": {"cpu_spike": 30, "latency": 20}},
}

_stop_flags: dict[str, bool] = {}


def targets() -> list[dict]:
    return [{"name": n, **cfg} for n, cfg in DEMO_TARGETS.items()]


def _insert_point_ts(name: str, value: float) -> None:
    with _conn() as con:
        con.execute("INSERT INTO telemetry_points(ts, name, value) VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?)",
                    (name, float(value)))


def start(target: str, fault_type: str = "latency", duration_s: int = 12, severity: int = 6) -> dict:
    cfg = DEMO_TARGETS.get(target)
    if cfg is None:
        raise LookupError(f"unknown demo target '{target}'")
    if fault_type not in cfg["faults"]:
        raise ValueError(f"fault must be one of {list(cfg['faults'])}")
    run_id = uuid.uuid4().hex[:12]
    metric = cfg["metric"]
    with _conn() as con:
        con.execute(
            "INSERT INTO aiops_chaos_runs(id, target, fault_type) VALUES (?,?,?)",
            (run_id, target, fault_type),
        )
    _stop_flags[run_id] = False

    def _run() -> None:
        baseline = cfg["baseline"]
        spike = cfg["faults"][fault_type]
        steps = max(int(duration_s * 2), 6)
        for i in range(steps):
            if _stop_flags.get(run_id, True):
                break
            noise = random.uniform(-0.2, 0.3) * baseline
            if i < int(steps * 0.6):
                value = baseline * spike + noise  # fault window
            else:
                value = baseline + noise  # recovery window
            _insert_point_ts(metric, value)
            time.sleep(0.5)
        with _conn() as con:
            con.execute("UPDATE aiops_chaos_runs SET status='ended', ended_at=datetime('now') WHERE id=?", (run_id,))

    threading.Thread(target=_run, daemon=True, name=f"chaos-{run_id}").start()
    return {"run_id": run_id, "target": target, "fault_type": fault_type,
            "metric": metric, "duration_s": duration_s}


def stop(run_id: str) -> bool:
    if run_id in _stop_flags:
        _stop_flags[run_id] = True
        return True
    return False


def stop_all_for(target: str) -> int:
    """Stop every active chaos run touching a target (used as the rollback)."""
    with _conn() as con:
        rows = con.execute("SELECT id FROM aiops_chaos_runs WHERE target=? AND status='running'", (target,)).fetchall()
    n = 0
    for r in rows:
        if stop(r["id"]):
            n += 1
            with _conn() as con:
                con.execute("UPDATE aiops_chaos_runs SET status='ended', ended_at=datetime('now') WHERE id=?", (r["id"],))
    return n


def state() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM aiops_chaos_runs ORDER BY started_at DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]
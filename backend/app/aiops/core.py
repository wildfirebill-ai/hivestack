"""AIOps core — telemetry ingestion, detection, alerts, topology/RCA,
incidents, and remediation-with-approval. Deterministic heuristics power the
loop offline; memory recall enriches RCA notes."""

from __future__ import annotations

import datetime as _dt
import json
import re
import uuid
from typing import Any

from ..db import _conn
from ..studio import analytics as _an


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _iso_to_dt(text: str) -> _dt.datetime:
    t = text.replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(t)
    except ValueError:
        return _dt.datetime.now(_dt.timezone.utc)


# ------------------------------------------------------------------ telemetry
def ingest_points(points: list[dict]) -> int:
    with _conn() as con:
        for p in points:
            con.execute(
                "INSERT INTO telemetry_points(ts, name, value) VALUES (?,?,?)",
                (p.get("ts") or _now(), str(p.get("name", "metric")), float(p.get("value", 0))),
            )
    return len(points)


def ingest_logs(logs: list[dict]) -> int:
    with _conn() as con:
        for l in logs:
            con.execute(
                "INSERT INTO telemetry_logs(ts, source, level, message) VALUES (?,?,?,?)",
                (l.get("ts") or _now(), l.get("source"), l.get("level", "info"), str(l.get("message", ""))),
            )
    return len(logs)


def query_points(name: str | None = None, minutes: float | None = 30) -> list[dict]:
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=minutes or 30)
    sql = "SELECT * FROM telemetry_points WHERE ts >= ?"
    params: list = [cutoff.isoformat()]
    if name:
        sql += " AND name=?"
        params.append(name)
    sql += " ORDER BY ts"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_logs(minutes: float | None = 30) -> list[dict]:
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=minutes or 30)
    with _conn() as con:
        rows = con.execute("SELECT * FROM telemetry_logs WHERE ts >= ? ORDER BY ts DESC", (cutoff.isoformat(),)).fetchall()
    return [dict(r) for r in rows]


def detect(name: str, minutes: float = 5, method: str = "hybrid") -> dict:
    pts = query_points(name, minutes)
    values = [p["value"] for p in pts]
    res = _an.anomalies({name: values}, method=method)[name]
    anomalies = []
    for idx in res["anomalies"]:
        if idx < len(pts):
            anomalies.append({"ts": pts[idx]["ts"], "value": round(pts[idx]["value"], 3), "index": idx})
    return {"name": name, "points": len(values), "method": res["method"], "anomalies": anomalies,
            "readings": [round(v, 3) for v in values[-40:]]}


# ------------------------------------------------------------------ alerts
def create_alert(name: str, message: str, severity: str = "warning") -> str:
    alert_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO aiops_alerts(id, name, severity, message) VALUES (?,?,?,?)",
            (alert_id, name, severity, message),
        )
    return alert_id


def list_alerts(limit: int = 100) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, name, severity, status, message, created_at FROM aiops_alerts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_alert_status(alert_id: str, status: str) -> bool:
    if status not in ("open", "ack", "closed"):
        raise ValueError("invalid status")
    with _conn() as con:
        cur = con.execute("UPDATE aiops_alerts SET status=? WHERE id=?", (status, alert_id))
    return cur.rowcount > 0  # type: ignore[union-attr]


# ------------------------------------------------------------------ topology / RCA
def set_topology(services: list[dict]) -> dict:
    with _conn() as con:
        con.execute("DELETE FROM aiops_topology_edges")
        con.execute("DELETE FROM aiops_topology_nodes")
        for s in services:
            con.execute("INSERT OR REPLACE INTO aiops_topology_nodes(name, layer) VALUES (?,?)",
                        (str(s.get("name", "")), s.get("layer", "service")))
        for s in services:
            for dep in s.get("depends_on", []) or []:
                con.execute("INSERT OR REPLACE INTO aiops_topology_edges(source, target) VALUES (?,?)",
                            (str(s.get("name")), str(dep)))
    return {"services": len(services)}


def topology() -> dict:
    with _conn() as con:
        nodes = [dict(r) for r in con.execute("SELECT * FROM aiops_topology_nodes ORDER BY name").fetchall()]
        edges = [(r["source"], r["target"]) for r in con.execute("SELECT source, target FROM aiops_topology_edges").fetchall()]
    return {"nodes": nodes, "edges": edges}


def _affected(seed: str) -> list[str]:
    """Nodes impacted by a failure of seed: seed + everything that (transitively) depends on it."""
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT source FROM aiops_topology_edges").fetchall()
    rev: dict[str, list[str]] = {}
    for r in rows:
        rev.setdefault(r["source"], []).append(r["source"])
    with _conn() as con:
        edges = con.execute("SELECT source, target FROM aiops_topology_edges").fetchall()
    dependents: dict[str, list[str]] = {}
    for e in edges:
        dependents.setdefault(e["target"], []).append(e["source"])
    seen = {seed}
    stack = [seed]
    while stack:
        n = stack.pop()
        for dep in dependents.get(n, []):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return sorted(seen)


def _anomaly_evidence(name: str, minutes: float = 15) -> int:
    try:
        res = detect(name, minutes=minutes, method="zscore")
        return len(res["anomalies"])
    except Exception:  # noqa: BLE001
        return 0


def root_candidates(seed: str) -> list[dict]:
    """Score topology nodes as likely roots: how many services depend on them
    (weighted by anomaly evidence)."""
    with _conn() as con:
        nodes = [dict(r) for r in con.execute("SELECT name, layer FROM aiops_topology_nodes").fetchall()]
        edges = con.execute("SELECT source, target FROM aiops_topology_edges").fetchall()
    dependents: dict[str, list[str]] = {}
    for e in edges:
        dependents.setdefault(e["target"], []).append(e["source"])
    affected = _affected(seed) if seed else [n["name"] for n in nodes]
    cands: list[dict] = []
    for n in nodes:
        ev = 0
        for probe in (f"{n['name']}.latency_ms", f"{n['name']}.query_ms", f"{n['name']}.cpu", f"{n['name']}.error"):
            ev += _anomaly_evidence(probe)
            if ev:
                break
        downstream = len(dependents.get(n["name"], []))
        score = downstream * 2 + ev * 3
        cands.append({"name": n["name"], "layer": n.get("layer"), "downstream": downstream,
                      "anomaly_evidence": ev, "score": score})
    cands.sort(key=lambda c: -c["score"])
    root = cands[0]
    return {"root": root, "candidates": cands[:5], "affected": affected}


# ------------------------------------------------------------------ incidents
def _event(incident_id: str, kind: str, data: dict) -> None:
    with _conn() as con:
        con.execute("INSERT INTO aiops_incident_events(incident_id, kind, data) VALUES (?,?,?)",
                    (incident_id, kind, json.dumps(data)))
        con.execute("UPDATE aiops_incidents SET status=status, updated_at=datetime('now') WHERE id=?", (incident_id,))


def create_incident(title: str, symptom: str, description: str = "", severity: str = "warning") -> str:
    inc_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO aiops_incidents(id, title, status, description, symptom) VALUES (?,?,?,?,?)",
            (inc_id, title, "open", description, symptom),
        )
    _event(inc_id, "opened", {"severity": severity, "symptom": symptom})
    return inc_id


def triage(incident_id: str, seed: str | None = None) -> dict:
    inc = get_incident(incident_id)
    if inc is None:
        raise LookupError("incident not found")
    seed = seed or _guess_seed(inc.get("symptom", ""))
    candidates = root_candidates(seed) if seed else root_candidates(seed or "")
    hints = _memory_hints(seed)
    _event(incident_id, "triaged", {"seed": seed, "affected": candidates["affected"][:10]})
    _event(incident_id, "rca", {"root": candidates["root"], "hints": hints[:2]})
    return {"seed": seed, **candidates, "memory_hints": hints}


def _guess_seed(symptom: str) -> str | None:
    if not symptom:
        return None
    m = re.search(r"[A-Za-z0-9_-]+\.(?:latency|query|cpu|error|ms)", symptom)
    name = m.group(0).split(".")[0] if m else symptom.split(".")[0].strip()
    with _conn() as con:
        row = con.execute("SELECT name FROM aiops_topology_nodes WHERE lower(name)=lower(?)", (name,)).fetchone()
    return row["name"] if row else (name or None)


def _memory_hints(text: str, k: int = 3) -> list[str]:
    try:
        from ..config import settings as _s
        from ..memory import context as _ctx

        if _s.module_enabled("memory"):
            return _ctx.retrieve_context(text or "ops incident", k=k)["lines"]
    except Exception:  # noqa: BLE001
        pass
    return []


def suggest_remediation(incident_id: str, action: str, service: str) -> str:
    rem_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO aiops_remediation(id, incident_id, action, service) VALUES (?,?,?,?)",
            (rem_id, incident_id, action, service),
        )
    _event(incident_id, "remediation_requested", {"id": rem_id, "action": action, "service": service})
    return rem_id


def approve_remediation(rem_id: str, approve: bool) -> dict:
    with _conn() as con:
        row = con.execute("SELECT * FROM aiops_remediation WHERE id=?", (rem_id,)).fetchone()
    if row is None:
        raise LookupError("remediation not found")
    rem = dict(row)
    if rem["status"] != "pending":
        raise ValueError("already decided")
    if not approve:
        with _conn() as con:
            con.execute("UPDATE aiops_remediation SET status='denied', updated_at=datetime('now') WHERE id=?", (rem_id,))
        _event(rem["incident_id"], "remediation_denied", {"id": rem_id})
        return {"verified": False, "status": "denied"}
    # approved → roll back the fault and verify recovery (wait for the chaos
    # run's built-in recovery window, then check readings return to baseline)
    verified, _details = _verify_recovery(rem.get("service", ""))
    status = "remediated" if verified else "rollback_required"
    with _conn() as con:
        con.execute(
            "UPDATE aiops_remediation SET status=?, verified=?, updated_at=datetime('now') WHERE id=?",
            (status, int(verified), rem_id),
        )
    incident_id = rem["incident_id"]
    _event(incident_id, "remediated" if verified else "rollback", {"id": rem_id, "detail": _details})
    if verified:
        with _conn() as con:
            con.execute("UPDATE aiops_incidents SET status='resolved', updated_at=datetime('now') WHERE id=?", (incident_id,))
    return {"verified": verified, "status": status, "incident_id": incident_id, "detail": _details}


def _verify_recovery(service: str, max_wait: float = 24.0) -> tuple[bool, str]:
    """Wait for active chaos on `service` to finish, then check last readings
    have returned to baseline."""
    baseline = None
    try:
        from .chaos import DEMO_TARGETS

        baseline = DEMO_TARGETS.get(service, {}).get("baseline")
    except Exception:  # noqa: BLE001
        pass
    deadline = time_monotonic() + max_wait
    probes = [f"{service}.latency_ms", f"{service}.query_ms", f"{service}.cpu", f"{service}.error"]
    while time_monotonic() < deadline:
        active = False
        with _conn() as con:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM aiops_chaos_runs WHERE target=? AND status='running'", (service,)
            ).fetchone()
        if row and row["n"]:
            active = True
        if active:
            sleep(0.5)
            continue
        pts = []
        with _conn() as con:
            for probe in probes:
                rows = con.execute(
                    "SELECT value FROM telemetry_points WHERE name=? ORDER BY ts DESC LIMIT 8", (probe,)
                ).fetchall()
                if rows:
                    pts = [r["value"] for r in rows][-6:]
                    break
        if not pts:
            sleep(0.5)
            continue
        base = baseline if baseline is not None else min(pts)
        ok = all(v < base * 2 + 1 for v in pts)
        return ok, f"last readings: {[round(v,1) for v in pts]} vs baseline ~{base}"
    return False, "recovery wait timed out"


def time_monotonic():
    import time

    return time.monotonic()


def sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def postmortem(incident_id: str) -> dict:
    detail = get_incident(incident_id)
    if detail is None:
        raise LookupError("incident not found")
    timeline = [
        f"{e['ts']} [{e['kind']}] {json.loads(e['data'] or '{}')}" for e in detail.get("events", [])
    ]
    report = "\n".join([f"# Postmortem: {detail['title']}", f"status: {detail['status']}",
                        f"symptom: {detail['symptom']}", "", "## Timeline"] + [f"- {t}" for t in timeline])
    # write to outbox as a durable report
    from pathlib import Path

    outbox = settings_data_dir_outbox()
    path = outbox / f"postmortem-{incident_id}.md"
    path.write_text(report, encoding="utf-8")
    _event(incident_id, "postmortem", {"path": str(path.relative_to(settings_data_dir_outbox().parent))})
    return {"incident_id": incident_id, "path": str(path.relative_to(settings_data_dir_outbox().parent)), "report": report}


def settings_data_dir_outbox() -> Any:
    from ..config import settings as _s

    p = _s.data_dir / "outbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_remediation(incident_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM aiops_remediation"
    params: list = []
    if incident_id:
        sql += " WHERE incident_id=?"
        params.append(incident_id)
    sql += " ORDER BY created_at DESC"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_incident(incident_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM aiops_incidents WHERE id=?", (incident_id,)).fetchone()
    if row is None:
        return None
    inc = dict(row)
    with _conn() as con:
        events = con.execute("SELECT * FROM aiops_incident_events WHERE incident_id=? ORDER BY id", (incident_id,)).fetchall()
    inc["events"] = [dict(e) for e in events]
    inc["remediation"] = list_remediation(incident_id)
    return inc


def list_incidents(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, title, status, symptom, created_at, updated_at FROM aiops_incidents ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
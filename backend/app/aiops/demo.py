"""AIOps demo — one call drives the full loop:
inject fault → auto-detect → alert → incident + RCA + remediation suggestion.
Then `approve_remediation` stops the fault and verifies recovery (exit criteria)."""

from __future__ import annotations

import random
import time

from ..db import _conn
from . import chaos as _chaos
from . import core as _core

_BASELINE_POINTS = 8


def _seed_baseline(metric: str, baseline: float) -> None:
    """Write a short known-good baseline window for the metric so the detector
    can compare the injected spike against it (a window that is entirely in the
    fault state looks 'normal' and is never flagged)."""
    with _conn() as con:
        for _ in range(_BASELINE_POINTS):
            noise = random.uniform(-0.15, 0.15) * baseline
            con.execute(
                "INSERT INTO telemetry_points(ts, name, value)"
                " VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?)",
                (metric, float(baseline + noise)),
            )
            time.sleep(0.1)


def run(target: str = "web-api", fault_type: str = "latency", duration_s: int = 12) -> dict:
    start = _chaos.start(target, fault_type, duration_s=duration_s)
    metric = start["metric"]
    baseline = start["baseline"]
    _seed_baseline(metric, baseline)
    time.sleep(2.5)

    det = _core.detect(metric, minutes=1, method="hybrid")
    if not det["anomalies"]:
        _chaos.stop(start["run_id"])
        return {"ok": False, "reason": "no anomalies detected", "detect": det}

    alert_id = _core.create_alert(
        name=f"{target}-{fault_type}",
        message=f"anomaly on {metric}: {len(det['anomalies'])} suspicious readings",
        severity="critical",
    )

    incident_id = _core.create_incident(
        title=f"{target} {fault_type} fault",
        symptom=metric,
        description=f"demo fault injection via chaos run {start['run_id']}",
        severity="critical",
    )
    triage = _core.triage(incident_id, seed=target)
    root = triage["root"]["name"]
    rem_id = _core.suggest_remediation(
        incident_id,
        action=f"restart {root} / stop fault injection on {target}",
        service=target,
    )
    return {
        "ok": True,
        "run_id": start["run_id"],
        "metric": metric,
        "anomalies": det["anomalies"][:10],
        "alert_id": alert_id,
        "incident_id": incident_id,
        "remediation_id": rem_id,
        "rca": {"root": triage["root"], "affected": triage["affected"][:8]},
        "memory_hints": triage["memory_hints"][:2],
    }
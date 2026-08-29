"""AIOps demo — one call drives the full loop:
inject fault → auto-detect → alert → incident + RCA + remediation suggestion.
Then `approve_remediation` stops the fault and verifies recovery (exit criteria)."""

from __future__ import annotations

import time

from . import chaos as _chaos
from . import core as _core


def run(target: str = "web-api", fault_type: str = "latency", duration_s: int = 12) -> dict:
    start = _chaos.start(target, fault_type, duration_s=duration_s)
    metric = start["metric"]
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
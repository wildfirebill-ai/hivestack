"""AIOps endpoints — telemetry, detection, alerts, topology/RCA, incidents,
remediation, chaos, and the one-shot demo loop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import security
from ..aiops import chaos, core, demo
from ..config import settings

router = APIRouter(prefix="/api/aiops", tags=["aiops"])
_auth = Depends(security.require_token)


def _require() -> None:
    if not settings.module_enabled("aiops"):
        raise HTTPException(status_code=403, detail="aiops module is disabled")


class TelemetryIn(BaseModel):
    points: list[dict] = []
    logs: list[dict] = []


class DetectIn(BaseModel):
    name: str
    minutes: float = 5
    method: str = "hybrid"


class AlertIn(BaseModel):
    name: str
    message: str = ""
    severity: str = "warning"


class StatusIn(BaseModel):
    status: str


class TopologyIn(BaseModel):
    services: list[dict]


class IncidentIn(BaseModel):
    title: str
    symptom: str = ""
    description: str = ""
    seed: str | None = None
    severity: str = "warning"


class DecideIn(BaseModel):
    approve: bool


class ChaosIn(BaseModel):
    target: str
    fault_type: str = "latency"
    duration_s: int = 12
    severity: int = 6


class DemoIn(BaseModel):
    target: str = "web-api"
    fault_type: str = "latency"


# ------------------------------------------------------------------ telemetry
@router.post("/telemetry")
def telemetry(body: TelemetryIn, _: str = _auth) -> dict:
    _require()
    pts = core.ingest_points(body.points)
    logs = core.ingest_logs(body.logs)
    return {"points": pts, "logs": logs}


@router.get("/telemetry")
def telemetry_query(name: str | None = None, minutes: float = 30, _: str = _auth) -> dict:
    return {"points": core.query_points(name, minutes), "logs": core.query_logs(minutes)}


@router.post("/analyze")
def analyze(body: DetectIn, _: str = _auth) -> dict:
    _require()
    return core.detect(body.name, body.minutes, body.method)


# ------------------------------------------------------------------ alerts
@router.get("/alerts")
def alerts(_: str = _auth) -> dict:
    return {"alerts": core.list_alerts()}


@router.post("/alerts")
def create_alert(body: AlertIn, _: str = _auth) -> dict:
    _require()
    return {"id": core.create_alert(body.name, body.message, body.severity)}


@router.post("/alerts/{alert_id}/status")
def alert_status(alert_id: str, body: StatusIn, _: str = _auth) -> dict:
    try:
        ok = core.set_alert_status(alert_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not ok:
        raise HTTPException(status_code=404, detail="alert not found")
    return {"id": alert_id, "status": body.status}


# ------------------------------------------------------------------ topology / rca
@router.post("/topology")
def set_topology(body: TopologyIn, _: str = _auth) -> dict:
    _require()
    return core.set_topology(body.services)


@router.get("/topology")
def get_topology(_: str = _auth) -> dict:
    return core.topology()


@router.get("/rca")
def rca(seed: str, _: str = _auth) -> dict:
    return core.root_candidates(seed)


# ------------------------------------------------------------------ incidents
@router.post("/incidents")
def create_incident(body: IncidentIn, _: str = _auth) -> dict:
    _require()
    inc_id = core.create_incident(body.title, body.symptom, body.description, body.severity)
    triage = core.triage(inc_id, body.seed)
    rem_id = core.suggest_remediation(
        inc_id,
        action=f"investigate {triage['root']['name']} and apply appropriate remediation",
        service=triage["root"]["name"],
    )
    return {"incident_id": inc_id, "remediation_id": rem_id, "triage": triage}


@router.get("/incidents")
def incidents(_: str = _auth) -> dict:
    return {"incidents": core.list_incidents()}


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, _: str = _auth) -> dict:
    inc = core.get_incident(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@router.post("/incidents/{incident_id}/postmortem")
def postmortem(incident_id: str, _: str = _auth) -> dict:
    _require()
    try:
        return core.postmortem(incident_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


# ------------------------------------------------------------------ remediation
@router.post("/remediation/{rem_id}/approve")
def approve_remediation(rem_id: str, body: DecideIn, user: str = _auth) -> dict:
    try:
        result = core.approve_remediation(rem_id, body.approve)
        from .. import governance

        governance.audit(user, "aiops.remediation.approve", rem_id, {"approve": body.approve, "verified": result.get("verified")})
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/remediation")
def remediation(incident_id: str | None = None, _: str = _auth) -> dict:
    return {"remediation": core.list_remediation(incident_id)}


# ------------------------------------------------------------------ chaos
@router.get("/chaos/targets")
def chaos_targets(_: str = _auth) -> dict:
    return {"targets": chaos.targets()}


@router.post("/chaos/start")
def chaos_start(body: ChaosIn, _: str = _auth) -> dict:
    _require()
    try:
        return chaos.start(body.target, body.fault_type, body.duration_s, body.severity)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/chaos/{run_id}/stop")
def chaos_stop(run_id: str, _: str = _auth) -> dict:
    return {"stopped": chaos.stop(run_id), "run_id": run_id}


@router.get("/chaos")
def chaos_state(_: str = _auth) -> dict:
    return {"runs": chaos.state()}


# ------------------------------------------------------------------ demo
@router.post("/demo")
def demo_run(body: DemoIn, _: str = _auth) -> dict:
    _require()
    return demo.run(body.target, body.fault_type)
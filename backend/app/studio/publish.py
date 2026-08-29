"""Content publishing — a human-approved publish job that writes to a local
outbox (channels land in Stage 8). Approval gate: create → pending_approval →
approve/deny → execute (approved) → published."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..config import settings
from ..db import _conn


def outbox_dir() -> Path:
    p = settings.data_dir / "outbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_job(title: str, body: str, targets: list[str] | None = None) -> dict:
    job_id = uuid.uuid4().hex[:12]
    with _conn() as con:
        con.execute(
            "INSERT INTO publish_jobs(id, title, body, targets, status) VALUES (?,?,?,?,?)",
            (job_id, title, body, json.dumps(targets or []), "pending_approval"),
        )
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM publish_jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM publish_jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def decide(job_id: str, approve: bool) -> dict:
    job = get_job(job_id)
    if job is None:
        raise LookupError("job not found")
    if job["status"] != "pending_approval":
        raise ValueError(f"job is {job['status']} — already decided")
    status = "approved" if approve else "denied"
    with _conn() as con:
        con.execute("UPDATE publish_jobs SET status=?, updated_at=datetime('now') WHERE id=?", (status, job_id))
    return get_job(job_id)  # type: ignore[return-value]


def execute(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise LookupError("job not found")
    if job["status"] == "approved":
        pass
    elif job["status"] == "published":
        raise ValueError("already published")
    else:
        raise ValueError(f"job is {job['status']} — must be approved first")
    path = outbox_dir() / f"{job_id}.md"
    header = f"# {job['title']}\n\n"
    targets = ", ".join(json.loads(job.get("targets") or "[]"))
    meta = f"*targets: {targets or 'outbox'}*\n\n"
    path.write_text(header + meta + (job.get("body") or ""), encoding="utf-8")
    with _conn() as con:
        con.execute("UPDATE publish_jobs SET status='published', updated_at=datetime('now') WHERE id=?", (job_id,))
    return {"id": job_id, "status": "published", "path": str(path.relative_to(settings.data_dir)), "preview": (header + meta)[:200]}
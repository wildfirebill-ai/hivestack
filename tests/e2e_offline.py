#!/usr/bin/env python
"""hivestack offline end-to-end suite.

Drives the whole platform against a fresh uvicorn with a temporary runtime dir,
asserting every exit criteria from Stages 1-11. No network, no model required.

Run:  python tests/e2e_offline.py [port]
Exit code is non-zero if any scenario fails.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

# Scenario names contain non-ASCII glyphs (→, ·) that crash under cp1252 stdout
# on Windows. Reconfigure stdout to UTF-8 so print() never dies on encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  [PASS] {name}")
    except Exception as exc:  # noqa: BLE001
        FAIL.append(name)
        print(f"  [FAIL] {name}: {exc}")


def pick_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else pick_port()
    base = f"http://127.0.0.1:{port}"
    tmp = Path(tempfile.mkdtemp(prefix="hsv-e2e-"))
    try:
        env = dict(os.environ)
        env.update(
            HIVESTACK_CONFIG_DIR=str(tmp / "config"),
            HIVESTACK_DATA_DIR=str(tmp / "data"),
            HIVESTACK_MODELS_DIR=str(tmp / "models"),
            HIVESTACK_ADMIN_USER="admin",
            HIVESTACK_ADMIN_PASSWORD="hivestack",
        )
        proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(ROOT / "backend")],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        client = httpx.Client(base_url=base, timeout=40)

        def wait_health():
            for _ in range(60):
                try:
                    if client.get("/health").status_code == 200:
                        return
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1)
            raise RuntimeError("server did not become healthy")

        wait_health()

        def tok() -> str:
            r = client.post("/api/auth/login", json={"username": "admin", "password": "hivestack"})
            return r.json()["token"]

        def H(t: str) -> dict:
            return {"Authorization": f"Bearer {t}"}

        t = tok()

        # ---- health & auth
        def h():
            r = client.get("/health")
            assert r.status_code == 200 and r.json()["status"] == "ok", r.text
        check("health", h)
        check("login + /me", lambda: assert_json(client.get("/api/auth/me", headers=H(t)), "user", "admin"))

        # ---- provider gate (cloud refused offline)
        def gate():
            r = client.post("/api/chat", headers=H(t), json={"message": "x", "provider": "openai"})
            assert r.status_code == 403, r.text
        check("gate: cloud provider 403 offline", gate)

        # ---- chat fallback
        def chatfb():
            r = client.post("/api/chat", headers=H(t), json={"message": "status", "provider": "fallback"})
            assert r.status_code == 200 and r.json()["source"] == "fallback", r.text
        check("chat: CPU fallback", chatfb)

        # ---- memory hybrid search
        def mem():
            r = client.post("/api/memory/notes", headers=H(t), json={"scope": "global", "title": "M40", "content": "M40 24GB Maxwell fp32 vllm-unsupported"})
            assert r.status_code == 200, r.text
            s = client.post("/api/memory/search", headers=H(t), json={"query": "maxwell vram gpu", "k": 3})
            hits = s.json().get("results", [])
            assert hits and hits[0]["title"] == "M40", s.text
        check("memory: hybrid search finds note", mem)

        # ---- skills generate + validate
        def skill():
            g = client.post("/api/skills/generate", headers=H(t), json={"description": "Summarize markdown notes into a cited report", "name": "note-summ", "use_llm": False})
            name = g.json()["skill"]["name"]
            v = client.post(f"/api/skills/{name}/validate", headers=H(t), json={})
            assert v.json()["score"] == 1.0, v.text
        check("skills: generate + validate(1.0)", skill)

        # ---- docs word build + audit
        def doc():
            r = client.post("/api/docs/word", headers=H(t), json={"title": "e2e", "sections": [{"heading": "h", "body": ["b"]}]})
            assert r.status_code == 200 and r.json()["audit"]["pass"], r.text
        check("docs: word build audit pass", doc)

        # ---- comms webhook + vault
        def comms():
            r = client.post("/api/channels/webhook/ingest", headers=H(t), json={"text": "hello", "from_id": "t"})
            assert r.status_code == 200 and r.json()["reply"], r.text
            v = client.post("/api/vault", headers=H(t), json={"name": "k", "value": "v"})
            assert v.status_code == 200, v.text
            g = client.post("/api/vault/get", headers=H(t), json={"name": "k"})
            assert g.json()["value"] == "v"
        check("comms: webhook + vault", comms)

        # ---- workflow with approval gate
        def wf():
            d = {"steps": [{"id": "a", "type": "tool", "tool": "calculator", "args": {"expression": "6*7"}},
                           {"id": "b", "type": "wait", "seconds": 0, "mode": "approval", "deps": ["a"]},
                           {"id": "c", "type": "tool", "tool": "calculator", "args": {"expression": "1+1"}, "deps": ["b"]}]}
            w = client.post("/api/workflows", headers=H(t), json={"name": "e2e-wf", "definition": d})
            rid = client.post(f"/api/workflows/{w.json()['workflow']['id']}/run", headers=H(t), json={}).json()["run_id"]
            for _ in range(40):
                st = client.get(f"/api/workflows/runs/{rid}", headers=H(t)).json()["status"]
                if st == "awaiting_approval":
                    break
                time.sleep(0.5)
            assert st == "awaiting_approval", st
            client.post(f"/api/workflows/runs/{rid}/approve", headers=H(t), json={"approve": True})
            for _ in range(40):
                st = client.get(f"/api/workflows/runs/{rid}", headers=H(t)).json()["status"]
                if st in ("completed", "failed"):
                    break
                time.sleep(0.5)
            assert st == "completed", st
        check("workflow: deps + approval gate → completed", wf)

        # ---- agent run lifecycle (engine-less → clean error) + verify gate
        def agent():
            r = client.post("/api/agents/tasks", headers=H(t), json={"goal": "compute", "max_steps": 2, "allowed_scopes": ["low"]})
            rid = r.json()["id"]
            st = None
            for _ in range(40):
                d = client.get(f"/api/agents/tasks/{rid}", headers=H(t)).json()
                st = d.get("status")
                if st in ("error", "budget_capped", "completed"):
                    break
                time.sleep(0.5)
            assert st in ("error", "budget_capped"), st
            ver = client.post(f"/api/governance/verify/{rid}", headers=H(t), json={})
            assert ver.status_code == 200
        check("agents: run lifecycle + verify gate", agent)

        # ---- AIOps full loop
        def aiops():
            client.post("/api/aiops/topology", headers=H(t), json={"services": [{"name": "db", "depends_on": []}, {"name": "web-api", "depends_on": ["db"]}]})
            d = client.post("/api/aiops/demo", headers=H(t), json={"target": "db", "fault_type": "latency"}).json()
            assert d["ok"] and d["incident_id"], d
            app = client.post(f"/api/aiops/remediation/{d['remediation_id']}/approve", headers=H(t), json={"approve": True}).json()
            assert app["verified"], app
            inc = client.get(f"/api/aiops/incidents/{d['incident_id']}", headers=H(t)).json()
            assert inc["status"] == "resolved", inc.get("status")
        check("aiops: fault → detect → approve → verified resolved", aiops)

        # ---- governance: budget cap + RBAC
        def gov():
            client.post("/api/governance/budget", headers=H(t), json={"daily_token_budget": 0, "budget_enabled": True})
            r = client.post("/api/agents/tasks", headers=H(t), json={"goal": "x", "max_steps": 1, "allowed_scopes": ["low"]})
            rid = r.json()["id"]
            time.sleep(2)
            assert client.get(f"/api/agents/tasks/{rid}", headers=H(t)).json()["status"] == "budget_capped"
            client.post("/api/governance/budget", headers=H(t), json={"daily_token_budget": 500000, "budget_enabled": True})
            client.post("/api/governance/users", headers=H(t), json={"name": "ops", "password": "opspass123", "role": "operator"})
            t2 = client.post("/api/auth/login", json={"username": "ops", "password": "opspass123"}).json()["token"]
            assert client.get("/api/governance/users", headers=H(t2)).status_code == 403
            sr = client.get("/api/governance/security-review", headers=H(t)).json()
            assert sr["score"] == 100, sr
        check("governance: budget cap + RBAC + security 100", gov)

        # ---- economy: off gate → enable → escrow
        def econ():
            assert client.get("/api/economy", headers=H(t)).status_code == 403
            client.post("/api/system/modules/economy", headers=H(t), json={"enabled": True})
            client.post("/api/economy/accounts", headers=H(t), json={"name": "alice", "seed": 50})
            client.post("/api/economy/accounts", headers=H(t), json={"name": "bot", "seed": 0})
            g = client.post("/api/economy/gigs", headers=H(t), json={"title": "task", "reward": 5, "owner": "alice"}).json()["gig_id"]
            client.post(f"/api/economy/gigs/{g}/claim", headers=H(t), json={"performer": "bot"})
            client.post(f"/api/economy/gigs/{g}/complete", headers=H(t), json={})
            client.post(f"/api/economy/gigs/{g}/settle", headers=H(t), json={"approver": "alice"})
            acc = {a["name"]: a for a in client.get("/api/economy/accounts", headers=H(t)).json()["accounts"]}
            assert acc["bot"]["balance"] == 5, acc
        check("economy: off-gate 403 + escrow settle", econ)

        # ---- publishing (approval-gated outbox) quick
        def pub():
            j = client.post("/api/publish/jobs", headers=H(t), json={"title": "x", "body": "b"}).json()["job"]["id"]
            assert client.post(f"/api/publish/jobs/{j}/execute", headers=H(t), json={}).status_code == 400
            client.post(f"/api/publish/jobs/{j}/approve", headers=H(t), json={"approve": True})
            ex = client.post(f"/api/publish/jobs/{j}/execute", headers=H(t), json={}).json()
            assert ex["status"] == "published", ex
        check("studio: publish approval → outbox", pub)

        ctrl = client.get("/health")
        assert ctrl.status_code == 200
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        print(f"\n=== offline e2e: {len(PASS)} passed, {len(FAIL)} failed ===")
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def assert_json(resp, key, value):
    assert resp.status_code == 200, resp.text
    assert resp.json().get(key) == value, resp.text


if __name__ == "__main__":
    sys.exit(main())
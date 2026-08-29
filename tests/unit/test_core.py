"""Unit tests for core hardening + key endpoints (pytest + FastAPI TestClient).

These run fully offline (provider-gated) and mirror the critical assertions of
the offline e2e suite at the router level for fast iteration.
"""

from __future__ import annotations

import pytest


def test_health_liveness(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_health_ready_checks_database(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["database"] == "ok"
    assert body["status"] == "ready"


def test_metrics_prometheus(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "hivestack_http_requests_total" in r.text


def test_gate_cloud_403_offline(client):
    r = client.post("/api/chat", headers=client.auth, json={"message": "x", "provider": "openai"})
    assert r.status_code == 403


def test_chat_fallback_source(client):
    r = client.post("/api/chat", headers=client.auth, json={"message": "status", "provider": "fallback"})
    assert r.status_code == 200
    assert r.json()["source"] == "fallback"


def test_system_usage_exports_cost(client):
    # create a couple fallback rows to have something to count
    client.post("/api/chat", headers=client.auth, json={"message": "hi", "provider": "fallback"})
    r = client.get("/api/system/usage?days=7", headers=client.auth)
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body
    assert "est_cost_usd" in body["totals"]
    assert "series" in body


def test_rate_limit_strict_auth(client):
    statuses = [
        client.post("/api/auth/login", json={"username": "admin", "password": "hivestack"}).status_code
        for _ in range(12)
    ]
    # strict per-IP limit on /api/auth is 10/min
    assert 429 in statuses


def test_require_auth_on_protected_route(client):
    # override the fixture's Authorization header to exercise the 401 path
    r = client.get("/api/system/modules", headers={"Authorization": ""})
    assert r.status_code == 401

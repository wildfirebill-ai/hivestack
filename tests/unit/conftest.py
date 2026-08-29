"""Shared pytest fixtures — isolated temp runtime dirs + a FastAPI TestClient."""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"


@pytest.fixture()
def client(tmp_path):
    """FastAPI TestClient pointed at isolated temp /config /data /models dirs."""
    import sys

    sys.path.insert(0, str(BACKEND))

    os.environ.setdefault("HIVESTACK_CONFIG_DIR", str(tmp_path / "config"))
    os.environ.setdefault("HIVESTACK_DATA_DIR", str(tmp_path / "data"))
    os.environ.setdefault("HIVESTACK_MODELS_DIR", str(tmp_path / "models"))
    os.environ.setdefault("HIVESTACK_ADMIN_USER", "admin")
    os.environ.setdefault("HIVESTACK_ADMIN_PASSWORD", "hivestack")

    # Import after env is set so Settings() picks it up.
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        # Clear in-process rate-limit buckets so cumulative logins across tests
        # don't trip the strict /api/auth limit.
        from app.ratelimit import reset_all

        reset_all()
        # admin login helper
        r = c.post("/api/auth/login", json={"username": "admin", "password": "hivestack"})
        token = r.json()["token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


def pytest_configure(config):
    import sys

    # ensure backend importable even if tests run from a different cwd
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

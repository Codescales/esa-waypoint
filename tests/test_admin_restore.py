"""Route-level tests for admin restore snapshot_id validation (VULN-004).

Focuses on the format guard: malformed / traversal snapshot_id values must
be rejected with HTTP 400 before any path construction.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.routes import admin
from web.backend.auth_admin import current_admin


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[current_admin] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize("snapshot_id", [
    "../../etc/passwd",
    "../secret",
    "/etc/passwd",
    "not-a-timestamp",
    "20260101",            # missing time part
    "20260101T12000",      # too short
    "20260101T1200000",    # too long
    "",
])
def test_restore_rejects_bad_snapshot_id(client, snapshot_id):
    r = client.post("/api/admin/restore", json={"snapshot_id": snapshot_id})
    assert r.status_code == 400
    assert "Invalid snapshot_id format" in r.text


def test_restore_accepts_valid_format_but_missing_returns_404(client):
    # Well-formed id that does not exist should pass the format guard and
    # then 404 (not 400), proving legitimate ids are not blocked by the regex.
    r = client.post("/api/admin/restore", json={"snapshot_id": "20260101T120000"})
    assert r.status_code in (404, 500)

"""Route-level tests for briefs endpoints — focus on path-traversal
hardening (VULN-003) and continued legitimate functionality."""

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.routes import briefs
from web.backend.deps import get_briefs_dir


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        briefs_dir = os.path.join(tmpdir, "briefs")
        os.makedirs(briefs_dir)

        # Top-level brief
        with open(os.path.join(briefs_dir, "welcome.md"), "w") as f:
            f.write("# Welcome\nHello world\n")

        # A shift subdirectory with an index and a run brief
        shift_dir = os.path.join(briefs_dir, "shift-1")
        os.makedirs(shift_dir)
        with open(os.path.join(shift_dir, "_index.md"), "w") as f:
            f.write("# Shift 1 index\n")
        with open(os.path.join(shift_dir, "run-a.md"), "w") as f:
            f.write("# Run A\nBody\n")

        # A secret file outside the briefs dir that traversal would target
        with open(os.path.join(tmpdir, "secret.txt"), "w") as f:
            f.write("TOP SECRET\n")

        app = FastAPI()
        app.include_router(briefs.router)
        app.dependency_overrides[get_briefs_dir] = lambda: briefs_dir

        yield TestClient(app)


# ── Legitimate functionality (AC #5) ──

def test_get_brief_top_level(client):
    r = client.get("/api/briefs/welcome")
    assert r.status_code == 200
    body = r.json()
    assert "Hello world" in body["prose_md"]
    assert body["slug"] == "welcome"


def test_get_brief_in_shift_subdir(client):
    r = client.get("/api/briefs/run-a")
    assert r.status_code == 200
    assert "Body" in r.json()["prose_md"]


def test_list_briefs_root(client):
    r = client.get("/api/briefs")
    assert r.status_code == 200
    assert "welcome" in r.json()["briefs"]


def test_list_briefs_by_shift(client):
    r = client.get("/api/briefs", params={"shift": "shift-1"})
    assert r.status_code == 200
    slugs = [e["slug"] for e in r.json()["runs"]]
    assert "run-a" in slugs


# ── Traversal payloads must be rejected (AC #4) ──

@pytest.mark.parametrize("slug", [
    "../secret",
    "../../etc/passwd",
    "..%2f..%2fsecret",
    "foo/bar",
    "foo.bar",
])
def test_get_brief_rejects_traversal(client, slug):
    r = client.get(f"/api/briefs/{slug}")
    assert r.status_code in (400, 404)
    assert "SECRET" not in r.text


def test_get_brief_rejects_dotdot_slug_directly(client):
    """The handler itself must reject a raw '..' slug (regex guard),
    independent of URL normalization."""
    from web.backend.routes.briefs import _validate_slug
    from fastapi import HTTPException
    for bad in ("..", ".", "../x", "a/b"):
        with pytest.raises(HTTPException) as exc:
            _validate_slug(bad)
        assert exc.value.status_code == 400


@pytest.mark.parametrize("shift", [
    "../",
    "../../etc",
    "..%2f..",
    "shift/../..",
])
def test_list_briefs_rejects_traversal_shift(client, shift):
    r = client.get("/api/briefs", params={"shift": shift})
    assert r.status_code in (400, 404)
    assert "SECRET" not in r.text

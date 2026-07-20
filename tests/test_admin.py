"""Tests for admin endpoints."""

import pytest


class TestAdminLogin:
    def test_login_success(self, client, monkeypatch):
        monkeypatch.setattr("web.backend.config.ADMIN_PASSWORD", "admin-pass")
        r = client.post("/api/admin/login", json={"password": "admin-pass"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_login_failure(self, client, monkeypatch):
        monkeypatch.setattr("web.backend.config.ADMIN_PASSWORD", "admin-pass")
        r = client.post("/api/admin/login", json={"password": "wrong"})
        assert r.status_code == 401


class TestAdminLogout:
    def test_logout(self, client, admin_cookies):
        r = client.post("/api/admin/logout", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_logout_unauthorized(self, unauth_client):
        r = unauth_client.post("/api/admin/logout")
        assert r.status_code == 401


class TestAdminStatus:
    def test_status(self, client, admin_cookies):
        r = client.get("/api/admin/status", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert data["db_exists"] is True
        assert data["db_healthy"] is True
        assert data["schema_version"] >= 5
        assert data["counts"]["runs"] >= 2
        assert data["counts"]["incentives"] >= 2

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/admin/status")
        assert r.status_code == 401


class TestAdminSnapshots:
    def test_list_snapshots(self, client, admin_cookies):
        r = client.get("/api/admin/snapshots", cookies=admin_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAdminRestore:
    def test_rejects_bad_snapshot_id(self, client, admin_cookies):
        r = client.post("/api/admin/restore", json={"snapshot_id": "../../etc/passwd"}, cookies=admin_cookies)
        assert r.status_code == 400

    def test_restore_not_found(self, client, admin_cookies):
        r = client.post("/api/admin/restore", json={"snapshot_id": "20260101T120000"}, cookies=admin_cookies)
        assert r.status_code == 404


class TestAdminAudit:
    def test_audit_log(self, client, admin_cookies):
        r = client.get("/api/admin/audit", cookies=admin_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAdminHosts:
    def test_list_hosts(self, client, admin_cookies):
        r = client.get("/api/admin/hosts", cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["name"] == "Anonymous Host"

    def test_create_host(self, client, admin_cookies):
        r = client.post("/api/admin/hosts", json={"name": "Test Host"}, cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["name"] == "Test Host"

    def test_create_duplicate_host(self, client, admin_cookies):
        client.post("/api/admin/hosts", json={"name": "Duplicate Host"}, cookies=admin_cookies)
        r = client.post("/api/admin/hosts", json={"name": "Duplicate Host"}, cookies=admin_cookies)
        assert r.status_code == 409

    def test_deactivate_host(self, client, admin_cookies):
        r = client.delete("/api/admin/hosts/1", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_deactivate_host_not_found(self, client, admin_cookies):
        r = client.delete("/api/admin/hosts/999", cookies=admin_cookies)
        assert r.status_code == 404


class TestAdminJobs:
    def test_list_jobs(self, client, admin_cookies):
        r = client.get("/api/admin/jobs", cookies=admin_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_job_not_found(self, client, admin_cookies):
        r = client.get("/api/admin/jobs/nonexistent", cookies=admin_cookies)
        assert r.status_code == 404

    def test_cancel_job_not_found(self, client, admin_cookies):
        r = client.post("/api/admin/jobs/nonexistent/cancel", cookies=admin_cookies)
        assert r.status_code == 404


class TestAdminPatchRunner:
    def test_patch_runner(self, client, admin_cookies):
        r = client.patch("/api/admin/runners/speedrunner1", json={"display_name": "Updated Name"}, cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["display_name"] == "Updated Name"

    def test_patch_runner_not_found(self, client, admin_cookies):
        r = client.patch("/api/admin/runners/nonexistent", json={"display_name": "x"}, cookies=admin_cookies)
        assert r.status_code == 404

    def test_patch_runner_empty_body(self, client, admin_cookies):
        r = client.patch("/api/admin/runners/speedrunner1", json={}, cookies=admin_cookies)
        assert r.status_code == 400


class TestAdminPatchRun:
    def test_patch_commentator(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.patch(f"/api/admin/runs/{slug}", json={"commentator": "New Commentator"}, cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["commentator"] == "New Commentator"

    def test_patch_runner_slugs(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.patch(f"/api/admin/runs/{slug}", json={"runner_slugs": ["speedrunner1"]}, cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data["participants"]) == 1
        assert data["participants"][0]["slug"] == "speedrunner1"

    def test_patch_runner_slugs_multiple(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.patch(f"/api/admin/runs/{slug}", json={"runner_slugs": ["speedrunner1", "speedrunner2"]}, cookies=admin_cookies)
        assert r.status_code == 200
        data = r.json()
        assert len(data["participants"]) == 2
        slugs = [p["slug"] for p in data["participants"]]
        assert "speedrunner1" in slugs
        assert "speedrunner2" in slugs

    def test_patch_run_not_found(self, client, admin_cookies):
        r = client.patch("/api/admin/runs/nonexistent", json={"commentator": "x"}, cookies=admin_cookies)
        assert r.status_code == 404

    def test_patch_run_empty_body(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.patch(f"/api/admin/runs/{slug}", json={}, cookies=admin_cookies)
        assert r.status_code == 400

    def test_patch_unauthorized(self, unauth_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = unauth_client.patch(f"/api/admin/runs/{slug}", json={"commentator": "x"})
        assert r.status_code == 401


class TestAdminCreateRun:
    def _payload(self, **overrides):
        payload = {
            "scheduled": "2026-07-20T10:00:00",
            "game": "Test Game",
            "category": "Any%",
            "estimate": "1:00:00",
            "stream": "stream1",
            "stream_short": "stream1",
        }
        payload.update(overrides)
        return payload

    def test_create_run(self, client, admin_cookies):
        r = client.post("/api/admin/runs", json=self._payload(), cookies=admin_cookies)
        assert r.status_code == 201
        data = r.json()
        assert data["game"] == "Test Game"
        assert data["category"] == "Any%"
        assert data["slug"]

    def test_create_run_with_runner_slugs(self, client, admin_cookies):
        r = client.post(
            "/api/admin/runs",
            json=self._payload(game="Test Game 2", runner_slugs=["speedrunner1"]),
            cookies=admin_cookies,
        )
        assert r.status_code == 201
        data = r.json()
        assert len(data["participants"]) == 1
        assert data["participants"][0]["slug"] == "speedrunner1"

    def test_create_duplicate_run(self, client, admin_cookies):
        payload = self._payload(game="Test Game 3")
        client.post("/api/admin/runs", json=payload, cookies=admin_cookies)
        r = client.post("/api/admin/runs", json=payload, cookies=admin_cookies)
        assert r.status_code == 409

    def test_create_unauthorized(self, unauth_client):
        r = unauth_client.post("/api/admin/runs", json=self._payload())
        assert r.status_code == 401


class TestAdminDeleteRun:
    def _create(self, client, admin_cookies, game="Deletable Game"):
        r = client.post(
            "/api/admin/runs",
            json={
                "scheduled": "2026-07-21T10:00:00",
                "game": game,
                "category": "Any%",
                "estimate": "1:00:00",
                "stream": "stream1",
                "stream_short": "stream1",
            },
            cookies=admin_cookies,
        )
        assert r.status_code == 201
        return r.json()["slug"]

    def test_delete_run(self, client, admin_cookies):
        slug = self._create(client, admin_cookies)
        r = client.delete(f"/api/admin/runs/{slug}", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r = client.get(f"/api/runs/{slug}", cookies=admin_cookies)
        assert r.status_code == 404

    def test_delete_run_not_found(self, client, admin_cookies):
        r = client.delete("/api/admin/runs/nonexistent", cookies=admin_cookies)
        assert r.status_code == 404

    def test_delete_run_with_incentives_blocked(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.delete(f"/api/admin/runs/{slug}", cookies=admin_cookies)
        assert r.status_code == 409

    def test_delete_unauthorized(self, unauth_client):
        r = unauth_client.delete("/api/admin/runs/some-slug")
        assert r.status_code == 401

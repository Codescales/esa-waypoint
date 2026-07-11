"""Tests for incentives endpoints."""

import pytest


class TestListIncentives:
    def test_list_all(self, client):
        r = client.get("/api/incentives")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2

    def test_filter_by_run_slug(self, client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.get("/api/incentives", params={"run_slug": slug})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["incentive_text"] == "100 coins bonus"

    def test_filter_by_status(self, client):
        r = client.get("/api/incentives", params={"status": "Active"})
        assert r.status_code == 200
        data = r.json()
        assert all(inc["status"] == "Active" for inc in data)

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/incentives")
        assert r.status_code == 401


class TestGetIncentive:
    def test_get_by_uuid(self, client):
        r = client.get("/api/incentives/inc-001")
        assert r.status_code == 200
        assert r.json()["incentive_text"] == "100 coins bonus"

    def test_not_found(self, client):
        r = client.get("/api/incentives/nonexistent")
        assert r.status_code == 404


class TestPatchIncentive:
    def test_patch_text(self, client):
        # Create a dedicated incentive for this patch test
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = client.post("/api/incentives", json={
            "run_slug": slug, "incentive_text": "patch-me",
        }).json()
        r = client.patch(f"/api/incentives/{created['uuid']}", json={"incentive_text": "updated"})
        assert r.status_code == 200
        assert r.json()["incentive_text"] == "updated"

    def test_patch_status_requires_admin(self, client):
        r = client.patch("/api/incentives/inc-001", json={"status": "Completed"})
        assert r.status_code == 422

    def test_patch_status_as_admin(self, client, admin_cookies):
        # Create a dedicated incentive so we don't corrupt inc-001 status for other tests
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = client.post("/api/incentives", json={
            "run_slug": slug, "incentive_text": "status-test",
        }).json()
        r = client.patch(f"/api/incentives/{created['uuid']}", json={"status": "Completed"}, cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["status"] == "Completed"

    def test_not_found(self, client):
        r = client.patch("/api/incentives/nonexistent", json={"incentive_text": "x"})
        assert r.status_code == 404


class TestCreateIncentive:
    def test_create(self, client, admin_cookies):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.post("/api/incentives", json={
            "run_slug": slug,
            "incentive_text": "new incentive",
            "incentive_category": "Target",
        }, cookies=admin_cookies)
        assert r.status_code == 201
        data = r.json()
        assert data["incentive_text"] == "new incentive"
        assert data["run_slug"] == slug

    def test_create_requires_admin(self, unauth_client):
        r = unauth_client.post("/api/incentives", json={
            "run_slug": "x", "incentive_text": "x",
        })
        assert r.status_code == 401


class TestDeleteIncentive:
    def test_delete(self, client, admin_cookies):
        # Create a fresh incentive to delete so seeded rows are untouched
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = client.post("/api/incentives", json={
            "run_slug": slug, "incentive_text": "delete-me",
        }).json()
        r = client.delete(f"/api/incentives/{created['uuid']}", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["status"] == "Removed"

    def test_delete_requires_admin(self, unauth_client):
        r = unauth_client.delete("/api/incentives/inc-001")
        assert r.status_code == 401

    def test_delete_not_found(self, client, admin_cookies):
        r = client.delete("/api/incentives/nonexistent", cookies=admin_cookies)
        assert r.status_code == 404

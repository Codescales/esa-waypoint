"""Tests for runs endpoints."""

import pytest


class TestListRuns:
    def test_list_all(self, client):
        r = client.get("/api/runs")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2

    def test_search_by_game(self, client):
        r = client.get("/api/runs", params={"search": "Mario"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["game"] == "Super Mario 64"

    def test_search_by_participant(self, client):
        r = client.get("/api/runs", params={"search": "SpeedRunner1"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1

    def test_search_no_match(self, client):
        r = client.get("/api/runs", params={"search": "Nonexistent"})
        assert r.status_code == 200
        assert r.json() == []

    def test_marathon_flag(self, client):
        r = client.get("/api/runs", params={"marathon": "true"})
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_filter_by_stream(self, client):
        r = client.get("/api/runs", params={"stream": "stream1"})
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/runs")
        assert r.status_code == 401


class TestGetRun:
    def test_get_by_slug(self, client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.get(f"/api/runs/{slug}")
        assert r.status_code == 200
        data = r.json()
        assert data["game"] == "Super Mario 64"
        assert data["slug"] == slug

    def test_get_run_has_participants(self, client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = client.get(f"/api/runs/{slug}")
        data = r.json()
        assert len(data["participants"]) == 2

    def test_not_found(self, client):
        r = client.get("/api/runs/nonexistent")
        assert r.status_code == 404

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/runs/some-slug")
        assert r.status_code == 401

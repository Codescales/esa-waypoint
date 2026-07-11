"""Tests for runners endpoints."""

import pytest


class TestListRunners:
    def test_list_all(self, client):
        r = client.get("/api/runners")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 3
        slugs = [d["slug"] for d in data]
        assert "speedrunner1" in slugs

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/runners")
        assert r.status_code == 401


class TestGetRunner:
    def test_get_by_slug(self, client):
        r = client.get("/api/runners/speedrunner1")
        assert r.status_code == 200
        assert r.json()["display_name"] == "SpeedRunner1"

    def test_not_found(self, client):
        r = client.get("/api/runners/nonexistent")
        assert r.status_code == 404


class TestGetRunnerProfile:
    def test_get_profile(self, client):
        r = client.get("/api/runners/speedrunner1/profile")
        assert r.status_code == 200
        assert r.json()["slug"] == "speedrunner1"

    def test_not_found(self, client):
        r = client.get("/api/runners/nonexistent/profile")
        assert r.status_code == 404


class TestGetRunnerPbs:
    def test_get_pbs(self, client):
        r = client.get("/api/runners/speedrunner1/pbs")
        assert r.status_code == 200
        assert r.json()["slug"] == "speedrunner1"

    def test_not_found(self, client):
        r = client.get("/api/runners/nonexistent/pbs")
        assert r.status_code == 404


class TestGetRunnerRuns:
    def test_get_runs(self, client):
        r = client.get("/api/runners/speedrunner1/runs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_not_found(self, client):
        r = client.get("/api/runners/nonexistent/runs")
        assert r.status_code == 200
        assert r.json() == []

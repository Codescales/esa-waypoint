"""Tests for auth endpoints."""

import pytest


class TestLogin:
    def test_login_success(self, client, monkeypatch):
        monkeypatch.setattr("web.backend.config.SHARED_PASSWORD", "host-pass")
        r = client.post("/api/login", json={"password": "host-pass"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert "esa_session" in r.cookies

    def test_login_failure(self, client, monkeypatch):
        monkeypatch.setattr("web.backend.config.SHARED_PASSWORD", "host-pass")
        r = client.post("/api/login", json={"password": "wrong"})
        assert r.status_code == 401

    def test_login_rate_limit(self, client, monkeypatch):
        monkeypatch.setattr("web.backend.config.SHARED_PASSWORD", "host-pass")
        for _ in range(5):
            client.post("/api/login", json={"password": "host-pass"})
        r = client.post("/api/login", json={"password": "host-pass"})
        assert r.status_code == 429


class TestLogout:
    def test_logout(self, client):
        r = client.post("/api/logout")
        assert r.status_code == 200
        assert r.json()["ok"] is True

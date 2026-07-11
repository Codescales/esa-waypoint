"""Tests for health endpoint."""

from web.backend.models import StaleInfo


class TestHealth:
    def test_health_returns_stale_info(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert "is_stale" in data
        assert "is_missing" in data
        assert data["is_missing"] is False

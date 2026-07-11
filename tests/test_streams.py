"""Tests for streams endpoint."""

import pytest


class TestListStreams:
    def test_list_streams(self, client):
        r = client.get("/api/streams")
        assert r.status_code == 200
        data = r.json()
        assert "2026 - Summer (Stream One)" in data

    def test_unauthorized(self, unauth_client):
        r = unauth_client.get("/api/streams")
        assert r.status_code == 401

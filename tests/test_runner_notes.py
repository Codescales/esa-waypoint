"""Tests for runner notes endpoints."""

import pytest


class TestListRunnerNotes:
    def test_list_notes_for_runner(self, notes_client):
        r = notes_client.get("/api/runner-notes", params={"runner_slug": "speedrunner1"})
        assert r.status_code == 200
        assert r.json() == []

    def test_list_notes_runner_not_found(self, notes_client):
        r = notes_client.get("/api/runner-notes", params={"runner_slug": "nonexistent"})
        assert r.status_code == 404

    def test_list_notes_requires_runner_slug(self, notes_client):
        r = notes_client.get("/api/runner-notes")
        assert r.status_code == 422


class TestCreateRunnerNote:
    def test_create_note(self, notes_client):
        r = notes_client.post("/api/runner-notes", json={"runner_slug": "speedrunner1", "body": "Test note"})
        assert r.status_code == 200
        data = r.json()
        assert data["body"] == "Test note"
        assert data["runner_slug"] == "speedrunner1"
        assert data["is_own"] is True

    def test_create_note_runner_not_found(self, notes_client):
        r = notes_client.post("/api/runner-notes", json={"runner_slug": "nonexistent", "body": "test"})
        assert r.status_code == 404

    def test_create_note_empty_body(self, notes_client):
        r = notes_client.post("/api/runner-notes", json={"runner_slug": "speedrunner1", "body": ""})
        assert r.status_code in (400, 422)


class TestUpdateRunnerNote:
    def test_update_own_note(self, notes_client):
        created = notes_client.post("/api/runner-notes", json={"runner_slug": "speedrunner1", "body": "Original"}).json()
        r = notes_client.patch(f"/api/runner-notes/{created['id']}", json={"body": "Updated"})
        assert r.status_code == 200
        assert r.json()["body"] == "Updated"

    def test_update_note_not_found(self, notes_client):
        r = notes_client.patch("/api/runner-notes/99999", json={"body": "test"})
        assert r.status_code == 404


class TestDeleteRunnerNote:
    def test_delete_own_note(self, notes_client):
        created = notes_client.post("/api/runner-notes", json={"runner_slug": "speedrunner1", "body": "To delete"}).json()
        r = notes_client.delete(f"/api/runner-notes/{created['id']}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_note_not_found(self, notes_client):
        r = notes_client.delete("/api/runner-notes/99999")
        assert r.status_code == 404

"""Tests for notes endpoints."""

import pytest


class TestGetActiveHost:
    def test_returns_active_host(self, notes_client):
        r = notes_client.get("/api/notes/active-host")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Anonymous Host"
        assert data["id"] >= 1


class TestListNotes:
    def test_list_notes_for_run(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = notes_client.get("/api/notes", params={"run_slug": slug})
        assert r.status_code == 200
        assert r.json() == []

    def test_list_notes_run_not_found(self, notes_client):
        r = notes_client.get("/api/notes", params={"run_slug": "nonexistent"})
        assert r.status_code == 404

    def test_list_notes_requires_run_slug(self, notes_client):
        r = notes_client.get("/api/notes")
        assert r.status_code == 422


class TestCreateNote:
    def test_create_note(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = notes_client.post("/api/notes", json={"run_slug": slug, "body": "Test note"})
        assert r.status_code == 200
        data = r.json()
        assert data["body"] == "Test note"
        assert data["run_slug"] == slug
        assert data["is_own"] is True

    def test_create_note_run_not_found(self, notes_client):
        r = notes_client.post("/api/notes", json={"run_slug": "nonexistent", "body": "test"})
        assert r.status_code == 404

    def test_create_note_empty_body(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = notes_client.post("/api/notes", json={"run_slug": slug, "body": ""})
        assert r.status_code in (400, 422)

    def test_create_note_whitespace_body(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        r = notes_client.post("/api/notes", json={"run_slug": slug, "body": "   "})
        assert r.status_code == 400


class TestUpdateNote:
    def test_update_own_note(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = notes_client.post("/api/notes", json={"run_slug": slug, "body": "Original"}).json()
        r = notes_client.patch(f"/api/notes/{created['id']}", json={"body": "Updated"})
        assert r.status_code == 200
        assert r.json()["body"] == "Updated"

    def test_update_note_not_found(self, notes_client):
        r = notes_client.patch("/api/notes/99999", json={"body": "test"})
        assert r.status_code == 404

    def test_update_note_empty_body(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = notes_client.post("/api/notes", json={"run_slug": slug, "body": "Original"}).json()
        r = notes_client.patch(f"/api/notes/{created['id']}", json={"body": ""})
        assert r.status_code in (400, 422)


class TestDeleteNote:
    def test_delete_own_note(self, notes_client):
        slug = "super-mario-64__120-star__2026-07-11T1200"
        created = notes_client.post("/api/notes", json={"run_slug": slug, "body": "To delete"}).json()
        r = notes_client.delete(f"/api/notes/{created['id']}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_note_not_found(self, notes_client):
        r = notes_client.delete("/api/notes/99999")
        assert r.status_code == 404

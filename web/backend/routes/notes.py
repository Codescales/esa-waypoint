"""Notes endpoints — list, create, update, delete.

Notes are per-run commentary from hosts. They carry the host name at
write time (denormalized in `host_name` on the row) so renames don't
rewrite history.

Phase 2.4 ships with a single "Anonymous Host" identity (seeded by
init_db). When OIDC/OAuth lands in a future phase, that flow replaces
the static host with the real authenticated user; existing notes
keep their denormalized host_name.

Auth model for v1: any host with the shared password can:
- Read all notes
- Create notes (attributed to the active host — Anonymous Host for now)
- Update/delete only notes they created (matched on host_id)
- Admin can update/delete any note
"""

import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth_admin import admin_cookie_name, validate_admin_session
from .. import config as app_config
from ..deps import get_repo, auth_required
from src.db import Host, Note, Run, make_engine
from src import audit as audit_log

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _db_path() -> str:
    """Read DB_PATH at request time so tests can override it."""
    return app_config.DB_PATH

TZ = ZoneInfo("Europe/Stockholm")
NOTE_BODY_MAX = 10_000  # PRD risk 10: cap at 10KB


# ── DTOs ──


class NoteDTO(BaseModel):
    id: int
    run_slug: str
    host_id: int
    host_name: str
    body: str
    created_at: str
    updated_at: str
    is_own: bool = False
    can_edit: bool = False


class NoteCreateRequest(BaseModel):
    run_slug: str
    body: str = Field(min_length=1, max_length=NOTE_BODY_MAX)
    host_id: Optional[int] = None  # if None, use active host from cookie


class NoteUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=NOTE_BODY_MAX)


def _now_naive() -> datetime:
    """Return current time as naive datetime in Europe/Stockholm (matches DB)."""
    return datetime.now(TZ).replace(tzinfo=None)


def _resolve_active_host_id(host_id: Optional[int], admin_session: str | None) -> int:
    """Determine which host_id to attribute a new note to.

    Priority:
    1. Explicit host_id in request (admin only — for cross-attribute)
    2. The "Anonymous Host" — id 1 — for everyone else
    3. Fallback: any active host, or reactivate/create the default

    Currently the only host is "Anonymous Host". When OIDC ships, this
    function reads the authenticated identity from the session.
    """
    engine = make_engine(_db_path())
    try:
        with Session(engine) as s:
            if host_id is not None:
                # Verify it exists and is active
                host = s.get(Host, host_id)
                if host is None or not host.is_active:
                    raise HTTPException(status_code=400, detail="Host not found or inactive")
                return host.id

            # First try: any active host
            active = s.exec(select(Host).where(Host.is_active == True)).first()
            if active is not None:
                return active.id

            # Second try: reactivate an inactive "Anonymous Host" if one exists
            existing_anon = s.exec(select(Host).where(Host.name == "Anonymous Host")).first()
            if existing_anon is not None:
                existing_anon.is_active = True
                s.add(existing_anon)
                s.commit()
                s.refresh(existing_anon)
                return existing_anon.id

            # Third try: create the default
            new_host = Host(
                name="Anonymous Host",
                is_active=True,
                created_at=_now_naive(),
            )
            s.add(new_host)
            s.commit()
            s.refresh(new_host)
            return new_host.id
    finally:
        engine.dispose()


def _note_to_dto(note: Note, run: Run, current_host_id: int, is_admin: bool) -> NoteDTO:
    is_own = note.host_id == current_host_id
    can_edit = is_own or is_admin
    return NoteDTO(
        id=note.id,
        run_slug=run.slug,
        host_id=note.host_id,
        host_name=note.host_name,
        body=note.body,
        created_at=note.created_at.isoformat(),
        updated_at=note.updated_at.isoformat(),
        is_own=is_own,
        can_edit=can_edit,
    )


def _resolve_current_host_id() -> int:
    """Get the host_id of the current 'active' host.

    Phase 2.4: always returns the first active host (Anonymous Host
    in the default seed). When OIDC lands, this reads the auth
    session and returns the matched host_id (creating the host row
    on first login if needed).
    """
    engine = make_engine(_db_path())
    try:
        with Session(engine) as s:
            active = s.exec(select(Host).where(Host.is_active == True)).first()
            if active is None:
                # Auto-create (defensive — init_db should have done this)
                h = Host(name="Anonymous Host", is_active=True, created_at=_now_naive())
                s.add(h)
                s.commit()
                s.refresh(h)
                return h.id
            return active.id
    finally:
        engine.dispose()


# ── Routes ──


class ActiveHostDTO(BaseModel):
    id: int
    name: str


@router.get("/active-host", response_model=ActiveHostDTO)
async def get_active_host():
    """Return the currently active host (the host that new notes will be attributed to).

    Phase 2.4: returns the first active host (Anonymous Host). When OIDC
    ships, this returns the authenticated user.
    """
    engine = make_engine(_db_path())
    try:
        with Session(engine) as s:
            active = s.exec(select(Host).where(Host.is_active == True)).first()
            if active is None:
                h = Host(name="Anonymous Host", is_active=True, created_at=_now_naive())
                s.add(h)
                s.commit()
                s.refresh(h)
                return ActiveHostDTO(id=h.id, name=h.name)
            return ActiveHostDTO(id=active.id, name=active.name)
    finally:
        engine.dispose()


@router.get("", response_model=list[NoteDTO])
async def list_notes(
    run_slug: str = Query(...),
    esa_session: str | None = Cookie(default=None),
    esa_admin_session: str | None = Cookie(default=None, alias="esa_admin_session"),
    _=auth_required,
):
    engine = make_engine(_db_path())
    try:
        current_host_id = _resolve_current_host_id()
        is_admin = validate_admin_session(esa_admin_session)
        with Session(engine) as s:
            run = s.exec(select(Run).where(Run.slug == run_slug)).first()
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            notes = s.exec(
                select(Note).where(Note.run_id == run.id).order_by(Note.created_at.desc())
            ).all()
            return [_note_to_dto(n, run, current_host_id, is_admin) for n in notes]
    finally:
        engine.dispose()


@router.post("", response_model=NoteDTO)
async def create_note(
    body: NoteCreateRequest,
    esa_admin_session: str | None = Cookie(default=None, alias="esa_admin_session"),
    _=auth_required,
):
    stripped = body.body.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Note body cannot be empty or whitespace")
    if len(body.body) > NOTE_BODY_MAX:
        raise HTTPException(status_code=400, detail=f"Note body exceeds {NOTE_BODY_MAX} chars")

    is_admin = validate_admin_session(esa_admin_session)
    engine = make_engine(_db_path())
    try:
        current_host_id = _resolve_current_host_id()
        with Session(engine) as s:
            run = s.exec(select(Run).where(Run.slug == body.run_slug)).first()
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            host_id = _resolve_active_host_id(body.host_id, esa_admin_session)
            host = s.get(Host, host_id)
            if host is None:
                raise HTTPException(status_code=500, detail="Host not found")
            now = _now_naive()
            note = Note(
                run_id=run.id,
                host_id=host.id,
                host_name=host.name,  # denormalize at write time
                body=stripped,
                created_at=now,
                updated_at=now,
            )
            s.add(note)
            s.commit()
            s.refresh(note)
            # Audit
            audit_log.write_audit(
                os.path.dirname(_db_path()),
                "note_create",
                f"run={run.slug} host={host.name} len={len(stripped)}",
            )
            return _note_to_dto(note, run, current_host_id, is_admin)
    finally:
        engine.dispose()


@router.patch("/{note_id}", response_model=NoteDTO)
async def update_note(
    note_id: int,
    body: NoteUpdateRequest,
    esa_admin_session: str | None = Cookie(default=None, alias="esa_admin_session"),
    _=auth_required,
):
    stripped = body.body.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Note body cannot be empty or whitespace")
    if len(body.body) > NOTE_BODY_MAX:
        raise HTTPException(status_code=400, detail=f"Note body exceeds {NOTE_BODY_MAX} chars")

    is_admin = validate_admin_session(esa_admin_session)
    engine = make_engine(_db_path())
    try:
        current_host_id = _resolve_current_host_id()
        with Session(engine) as s:
            note = s.get(Note, note_id)
            if note is None:
                raise HTTPException(status_code=404, detail="Note not found")
            if note.host_id != current_host_id and not is_admin:
                raise HTTPException(status_code=403, detail="Can only edit own notes")
            run = s.get(Run, note.run_id)
            note.body = stripped
            note.updated_at = _now_naive()
            s.add(note)
            s.commit()
            s.refresh(note)
            audit_log.write_audit(
                os.path.dirname(_db_path()),
                "note_update",
                f"id={note_id} host={note.host_name}",
            )
            return _note_to_dto(note, run, current_host_id, is_admin)
    finally:
        engine.dispose()


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    esa_admin_session: str | None = Cookie(default=None, alias="esa_admin_session"),
    _=auth_required,
):
    is_admin = validate_admin_session(esa_admin_session)
    engine = make_engine(_db_path())
    try:
        current_host_id = _resolve_current_host_id()
        with Session(engine) as s:
            note = s.get(Note, note_id)
            if note is None:
                raise HTTPException(status_code=404, detail="Note not found")
            if note.host_id != current_host_id and not is_admin:
                raise HTTPException(status_code=403, detail="Can only delete own notes")
            run = s.get(Run, note.run_id)
            host_name = note.host_name
            s.delete(note)
            s.commit()
            audit_log.write_audit(
                os.path.dirname(_db_path()),
                "note_delete",
                f"id={note_id} host={host_name} run={run.slug if run else '?'}",
            )
            return {"ok": True}
    finally:
        engine.dispose()

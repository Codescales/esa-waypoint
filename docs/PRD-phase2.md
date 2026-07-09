# Phase 2 PRD: SQLite-Backed Incentives + Host Notes

**Status:** Draft
**Date:** 2026-07-05
**Phase:** 2 of 3 (Phase 1 = web viewer MVP, Phase 3 = TBD)
**Owner:** TBD

---

## 1. Executive Summary

Phase 1 shipped a read-only web viewer for ESA hosts: marathon view, schedule, incentives, and per-run briefs render from the existing `output/incentive_plan.xlsx` via a FastAPI + Next.js stack. Hosts can read but not interact.

Phase 2 makes the data interactive. Two additions:

1. **SQLite-backed data layer.** Incentives move from the XLSX spreadsheet into a SQLite database (`output/esa.db`). The web viewer reads from SQLite, not the spreadsheet. The XLSX becomes a raw import source. This unlocks:
   - Per-incentive editing from the web UI
   - A refresh/restore lifecycle with snapshots
   - Same `IncentiveRepo` Protocol seam — backend routes are unchanged

2. **Host notes.** Per-host notes attached to each run. The shared password becomes a host-identity picker: at login, the host picks their name from a list maintained by the operator. Notes are attributed and timestamped.

The two are bundled because notes are useless without persistent storage, and the SQLite store is the natural place for both. Phase 2 ends with hosts able to edit incentive metadata from their phone during a live run, with operator-gated refresh/restore and per-host note attribution.

---

## 2. Mission

**Make ESA host prep a live, two-way workflow** — hosts contribute to the data (notes, incentive status) during a marathon, not just consume it.

### Core Principles

1. **Read from DB, import from XLSX.** The XLSX is the upstream contract from Oengus/Horaro. The DB is the working set. Don't blur the boundary.
2. **Snapshots before imports.** Never lose work. Every refresh snapshots the current DB; restore is one click.
3. **Per-host attribution matters.** A note from "Kirthar's handler" is different from "the host who happened to be on shift." Notes carry identity, even when the auth model is shared-password.
4. **Operator-gated, host-visible.** Refresh/restore/edit-all are admin-only. Per-incentive edits and note creation are host-allowed.
5. **The repo seam earns its keep.** `XlsxIncentiveRepo` (read-only, v1) and `SqliteIncentiveRepo` (read-write, v2) implement the same Protocol. No route changes when we swap.

---

## 3. Target Users

### Primary: Host (10-15 per event)

**Comfort level:** High — speedrun community, familiar with the schedule spreadsheet, runs Oengus/Horaro.

**Needs:**
- View upcoming runs and incentives on phone during marathon
- Take notes on a run (interview material, runner quirks, tech issues)
- Update incentive status as it gets reviewed live ("this is approved", "this needs review")

**Pain today:** Stuck in the spreadsheet or a Slack thread. No attribution, no real-time, no mobile UI.

### Secondary: Operator (1-2 per event)

**Comfort level:** High — runs the pipeline, knows the data model.

**Needs:**
- Refresh the data when the schedule changes (run `python -m src.pipeline`, then import)
- Restore to a known-good state if an import goes wrong
- Maintain the list of authorized host identities

**Pain today:** Manual file manipulation. No audit trail of changes.

### Out of scope for users

Donors, runners, viewers — they don't access the web viewer.

---

## 4. MVP Scope

### In Scope (Phase 2)

**Data layer**
- [ ] SQLModel schema for `run`, `incentive`, `submission`, `host`, `note`, `snapshot`
- [ ] `SqliteIncentiveRepo` implementing the `IncentiveRepo` Protocol from `web/backend/repo.py`
- [ ] `src/import_to_sqlite.py` CLI: import xlsx → sqlite, with snapshot before write
- [ ] `src/snapshot.py` helper: create, list, restore snapshots
- [ ] Repo selection via env var (`REPO_TYPE=sqlite` | `xlsx`); default to `sqlite` after first import

**Admin operations (separate `ADMIN_PASSWORD`)**
- [ ] `POST /api/admin/login` → admin session cookie
- [ ] `POST /api/admin/logout`
- [ ] `POST /api/admin/refresh` — snapshot current DB, then import xlsx
- [ ] `POST /api/admin/restore?snapshot=<id>` — restore from snapshot
- [ ] `GET /api/admin/snapshots` — list available snapshots
- [ ] `GET /api/admin/status` — DB stats (run count, incentive count, last import time, db size)
- [ ] `GET /api/admin/hosts` / `POST /api/admin/hosts` / `DELETE /api/admin/hosts/{id}` — host CRUD

**Incentive editing (host + admin)**
- [ ] `PATCH /api/incentives/{uuid}` — update category, valid_for_game, status, estimate
- [ ] `GET /api/incentives/{uuid}` — fetch single incentive (for refresh after edit)
- [ ] `GET /api/incentives/diff?since=<timestamp>` — list changes since timestamp (for UI badges)

**Notes (host + admin)**
- [ ] `POST /api/notes` — create note (run_id, host_id, body)
- [ ] `GET /api/notes?run_slug=<slug>` — list notes for a run
- [ ] `PATCH /api/notes/{id}` — edit own note
- [ ] `DELETE /api/notes/{id}` — delete own note (admin can delete any)

**Frontend**
- [ ] Admin panel page (`/admin`): refresh button, restore dropdown, snapshot list, host CRUD, DB status
- [ ] Login flow: pick host identity after shared password (existing `SHARED_PASSWORD` + new `ADMIN_PASSWORD` for admin)
- [ ] Per-run notes panel on the run detail page: list, add, edit, delete
- [ ] Incentive editor on the run detail page: inline form to update category/valid/status/estimate
- [ ] "Edited" badge on incentives that have been modified (via diff endpoint)
- [ ] Note attribution: show host name and timestamp on each note

**Deployment**
- [ ] Docker compose: backend mounts `output/` read-write (DB needs write access)
- [ ] Migration script: detect existing xlsx + briefs setup, prompt to seed DB
- [ ] README updates: admin password setup, host identity management

### Out of Scope (deferred to Phase 3+)

- [ ] Real-time push (websockets, SSE) — for now, polling on focus
- [ ] Brief generation from UI — still CLI/skill-driven
- [ ] Editing runs themselves (only incentives + notes in v2)
- [ ] Per-host password accounts (still shared password + identity pick)
- [ ] Audit log (who changed what when) — beyond basic note attribution
- [ ] Multi-event support (only one marathon at a time)
- [ ] Host invite flow (operator manually adds host names)
- [ ] Note formatting (markdown) — plain text for v2
- [ ] Offline support / PWA
- [ ] Mobile push notifications
- [ ] Slack/Discord integration
- [ ] Tests for new code — but see "Quality" in section 11

---

## 5. User Stories

### Hosts

1. **As a host**, I want to take notes on a run during a marathon, so that I can remember details (interview material, runner quirks) for the next run.
   - *Example:* "Kirthar mentioned the run is harder than expected. WR might fall — note for the WR bidwar."

2. **As a host**, I want to mark an incentive as Approved from my phone, so that the fundraising team has real-time status without waiting for the spreadsheet.
   - *Example:* "Reward: Cuphead DLC bonus run — approved at 19:45."

3. **As a host**, I want to see who wrote each note, so that I know which host I can follow up with.
   - *Example:* "Note by Sarah at 21:10 — 'Kirthar will do an encore after the run.'"

4. **As a host**, I want to filter incentives to see only those needing review, so that I can prioritize my time.
   - *Example:* "Show me all 'In Review' incentives for the next 2 hours."

### Operators

5. **As an operator**, I want to refresh the schedule when Horaro changes, so that the web viewer stays current without redeploying.
   - *Example:* "Horaro updated a 15-minute delay. Run `python -m src.pipeline`, then click 'Refresh' in admin."

6. **As an operator**, I want to restore a snapshot if an import goes wrong, so that I can roll back without manual file recovery.
   - *Example:* "The refresh imported 0 incentives due to a bad xlsx. Restore from `snapshot-2026-08-01T1400`."

7. **As an operator**, I want to manage the list of host identities, so that notes are attributed correctly.
   - *Example:* "Add 'Sarah' as a host. Remove 'ex-volunteer' from last event."

8. **As an operator**, I want to see DB health (size, last import, row counts), so that I can detect issues early.
   - *Example:* "Last import was 6 hours ago. Run count: 176. Incentive count: 88."

### Technical

9. **As the system**, I want the `SqliteIncentiveRepo` to implement the same Protocol as `XlsxIncentiveRepo`, so that route handlers don't need to know which repo is active.

10. **As the system**, I want every import to snapshot the current DB first, so that bad imports are recoverable in one click.

---

## 6. Core Architecture & Patterns

### Repository seam

The `IncentiveRepo` Protocol defined in Phase 1 (`web/backend/repo.py`) is the data access layer. Phase 2 adds `SqliteIncentiveRepo` alongside `XlsxIncentiveRepo`. Selection via env var:

```python
# web/backend/deps.py
def get_repo(request: Request) -> IncentiveRepo:
    if config.REPO_TYPE == "sqlite":
        return SqliteIncentiveRepo(config.DB_PATH)
    return XlsxIncentiveRepo(config.SPREADSHEET_PATH)
```

Routes do not change.

### Snapshot pattern

Every admin `POST /api/admin/refresh` creates a snapshot first:

```python
# src/snapshot.py
def create_snapshot(db_path: str) -> Snapshot:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    snapshot_path = f"{db_path}.snapshot-{timestamp}"
    shutil.copy2(db_path, snapshot_path)
    return Snapshot(id=timestamp, path=snapshot_path, ...)
```

Restore is a file copy back. Snapshots are listed via the admin endpoint and can be deleted by the operator (manually via shell — not a UI feature in v2).

### Host identity model

Shared password auth + identity pick. Login flow:

1. User enters `SHARED_PASSWORD` at `/login`
2. If they have admin password, they can also enter it (separate field, optional)
3. After password(s) accepted, if not admin, show "Pick your name" step
4. Selected host ID stored on session
5. All notes created in that session carry the host_id

Implementation: keep using `sessionStorage` for password acceptance (Phase 1 model). Add a separate `esa-host-id` key in `sessionStorage` for identity pick. Admin auth is a third key `esa-admin=1`.

### Project structure (additions)

```
src/
├── db.py                    # SQLModel engine, init_db, get_session
├── import_to_sqlite.py      # xlsx → sqlite import CLI
├── snapshot.py              # create, list, restore

web/backend/
├── repo_sqlite.py           # SqliteIncentiveRepo
├── routes/
│   ├── admin.py             # admin operations
│   ├── notes.py             # notes CRUD
│   └── incentives.py        # add PATCH endpoint
├── auth_admin.py            # admin session validation

web/frontend/
├── app/admin/page.tsx       # admin panel
├── lib/api_admin.ts         # admin API client
├── lib/api_notes.ts         # notes API client
├── components/
│   ├── IncentiveEditor.tsx
│   ├── NotesPanel.tsx
│   └── HostPicker.tsx
```

### Database schema (SQLModel)

```python
class Run(SQLModel, table=True):
    id: int (PK, autoincrement)  # internal DB id
    pick: int
    scheduled: datetime
    game: str
    category: str
    estimate: str
    runner_display: str
    runner_twitch: str = ""
    runner_discord: str = ""
    runner_twitter: str = ""
    stream: str
    stream_short: str
    submission_id: Optional[str] = None
    category_id: Optional[str] = None
    incentives: str = ""  # raw text
    commentator: str = ""
    pronouns: str = ""
    slug: str  # derived, indexed, NOT the join key
    run_key: str  # UNIQUE — "submission_id|game|category" or "no-sub|game|category"
    imported_at: datetime  # last import time
    updated_at: datetime  # last edit time (in DB)

class Incentive(SQLModel, table=True):
    uuid: str (PK)  # matches xlsx UUID for continuity
    run_id: int (FK → Run.id)
    incentive_text: str
    incentive_category: str  # Reward / Poll-Bid War / Target
    valid_for_game: str  # Yes / No / Needs Review
    incentive_estimate: str = ""
    needs_approval: str = ""
    status: str  # To-Do / In Review / Approved / Removed
    submission_id: str = ""
    imported_at: datetime
    updated_at: datetime

class Host(SQLModel, table=True):
    id: int (PK, autoincrement)
    name: str  # mutable, unique among active hosts
    is_active: bool = True  # soft-delete
    created_at: datetime

class Note(SQLModel, table=True):
    id: int (PK, autoincrement)
    run_id: int (FK → Run.id)
    host_id: int (FK → Host.id)  # soft reference — denormalized host_name below
    host_name: str  # denormalized at write time
    body: str  # capped at 10KB
    created_at: datetime
    updated_at: datetime

class Snapshot(SQLModel, table=True):
    id: str (PK)  # ISO timestamp, e.g. "20260801T140000"
    path: str  # relative to output/, e.g. "snapshots/esa.db.20260801T140000"
    size_bytes: int
    reason: str  # "pre-import" / "pre-restore" / "manual"
    created_at: datetime
    schema_version: int  # for compatibility check on restore

class AdminAudit(SQLModel, table=True):  # not in DB, written to admin_audit.log
    timestamp: datetime
    action: str  # "refresh" / "restore" / "host_add" / etc.
    detail: str  # JSON or free text
```

The DB has a `schema_version` pragma. Routes check it on read; mismatch returns 503 with "run migrations" message. Migrations are forward-only, scripted.

---

## 7. Tools/Features

### Admin panel (`/admin`)

Single page with sections:
- **Status:** DB size, last import time, run count, incentive count, note count, snapshot count
- **Refresh:** button with confirm modal. On click: snapshot current, then import xlsx → sqlite. Show result (rows added/updated/removed).
- **Restore:** dropdown of snapshots with timestamp. Click → confirm → restore. Show result.
- **Snapshots:** list of snapshots with size and age. Manual cleanup (shell).
- **Hosts:** table of host names. Add/remove via form.

Gated by admin session. Non-admins get a 403.

### Run detail page additions

Below the existing brief content, two new sections:

**Incentive editor (collapsible per incentive):**
- Category dropdown (Reward / Poll-Bid War / Target / blank)
- Valid for game dropdown (Yes / No / Needs Review / blank)
- Status dropdown (To-Do / In Review / Needs Information / Approved / Removed)
- Estimate (text input)
- Save button per incentive
- "Edited" badge if changed since last import (from diff endpoint)

**Notes panel:**
- List of existing notes (newest first)
- Each note: host name, timestamp, body, edit/delete buttons (own notes only)
- Add note: textarea + submit
- Empty state: "No notes yet"

### Login flow

Step 1: password (existing). Step 2 (if not admin): pick host identity. Step 3 (if admin): skip host pick, mark as admin.

Stored in `sessionStorage`:
- `esa-auth=1` — password accepted
- `esa-host-id=<id>` — selected host
- `esa-admin=1` — admin session

Logout clears all three.

---

## 8. Technology Stack

### New dependencies

**Backend (add to `web/backend/pyproject.toml`):**
- `sqlmodel>=0.0.16` — type-safe ORM with Pydantic integration
- `aiosqlite>=0.20` — async SQLite driver (FastAPI is async)
- `pydantic-settings>=2` — env var management (already have pydantic)

**Frontend (add to `web/frontend/package.json`):**
- No new major dependencies. Use existing React + fetch.

### No changes to

- Horaro API client
- Oengus API client
- Pipeline CLI
- Brief generation (still reads xlsx via `brief.py`)
- Docker base images

---

## 9. Security & Configuration

### Authentication

Two passwords, both env vars:
- `SHARED_PASSWORD` — host access (existing)
- `ADMIN_PASSWORD` — admin operations (new)

Sessions stored in `sessionStorage` (client-side). Admin flag is a separate key. Backend has a `current_admin` dependency that checks the admin session via a separate cookie (not `esa_session` — that's been deprecated in Phase 1; we use `sessionStorage` and forward a header).

Wait — the sessionStorage model means the backend can't directly verify admin status. The backend trusts the frontend (Phase 1 architecture). For admin operations, we need backend trust too.

**Approach:** Add a server-side admin check using a shared secret header. The frontend sends `X-Admin-Token: <hmac>` on admin requests, signed with a key derived from `ADMIN_PASSWORD`. The backend verifies the HMAC. This keeps the password out of the client bundle.

Actually, simpler: the backend gets a `X-Admin-Token` header that is the `ADMIN_PASSWORD` itself, sent only over HTTPS in production. In dev, fine. The token is held in `sessionStorage` like the host password is currently.

Or even simpler: send the password in the request body for admin actions, and have the backend re-verify. This means the password is in every admin request. Not great for caching, but the routes are infrequent.

Best: HMAC of `(timestamp + admin_password)`, sent as header. Backend verifies HMAC. This prevents replay attacks.

Let me defer the exact mechanism to implementation — the design constraint is "admin operations require a separate password that the backend can verify without trusting the frontend blindly."

### Configuration

New env vars (added to `.env.example`):
```
ADMIN_PASSWORD=
DB_PATH=output/esa.db
REPO_TYPE=sqlite
SNAPSHOT_KEEP=10  # how many snapshots to retain on refresh
```

### Security scope

In scope:
- Admin operations require `ADMIN_PASSWORD`
- Notes are scoped to host_id (own notes editable/deletable)
- Admin can delete any note

Out of scope:
- Per-host passwords
- TLS termination (operator's reverse proxy)
- Rate limiting (LAN-scale traffic)
- Note encryption

---

## 10. API Specification

### Admin

```
POST /api/admin/login
  Body: { password: string }
  Sets: admin_token cookie or sessionStorage
  Returns: { ok: true } | 401

POST /api/admin/logout
  Clears admin session
  Returns: { ok: true }

GET  /api/admin/status
  Returns: {
    db_size_bytes: int,
    last_import_at: ISO datetime | null,
    counts: { runs: int, incentives: int, notes: int, hosts: int, snapshots: int }
  }

POST /api/admin/refresh
  Body: {} (uses configured xlsx path)
  Returns: {
    snapshot_id: string,
    rows_added: int,
    rows_updated: int,
    rows_removed: int,
    duration_ms: int
  }

GET  /api/admin/snapshots
  Returns: [
    { id: "20260801T140000", path: "...", size_bytes: int, age_hours: float }
  ]

POST /api/admin/restore
  Body: { snapshot_id: string }
  Returns: { ok: true, restored_from: snapshot_id }

GET  /api/admin/hosts
POST /api/admin/hosts
  Body: { name: string }
DELETE /api/admin/hosts/{id}
```

### Notes

```
GET   /api/notes?run_slug=<slug>
  Returns: [
    { id: int, run_slug: string, host_id: int, host_name: string,
      body: string, created_at: ISO, updated_at: ISO, is_own: bool }
  ]

POST  /api/notes
  Body: { run_slug: string, body: string }
  Returns: NoteDTO

PATCH /api/notes/{id}
  Body: { body: string }
  Returns: NoteDTO (must be own note, or admin)

DELETE /api/notes/{id}
  Returns: 204 (own note or admin)
```

### Incentives (additions)

```
PATCH /api/incentives/{uuid}
  Body: {
    incentive_category?: string,
    valid_for_game?: string,
    status?: string,
    incentive_estimate?: string
  }
  Returns: IncentiveDTO

GET   /api/incentives/{uuid}
  Returns: IncentiveDTO (for post-edit refresh)

GET   /api/incentives/diff?since=<ISO>
  Returns: { uuid: string, field: string, old: any, new: any }[]
```

### Auth on these endpoints

- All require host session (current `esa-auth=1`)
- PATCH/DELETE on notes also require ownership (or admin)
- PATCH on incentives: any host
- All `/api/admin/*` require admin session

---

## 11. Success Criteria

### MVP success definition

A host can: open `/run/cuphead__any-1-1-regular__2026-08-01T2020` on their phone, mark an incentive as Approved, add a note attributed to themselves, and see both reflected in the UI within 2 seconds. An operator can: open `/admin`, click Refresh, see the import complete, and restore from a previous snapshot if needed.

### Functional requirements

- [ ] `SqliteIncentiveRepo` reads all data currently served by `XlsxIncentiveRepo`
- [ ] Host can edit incentive status/category/valid/estimate and see the change immediately
- [ ] Host can add a note attributed to their picked identity
- [ ] Host can edit/delete only their own notes
- [ ] Admin can refresh xlsx → sqlite with a snapshot first
- [ ] Admin can restore from a snapshot in one click
- [ ] Admin can add/remove host identities
- [ ] Existing xlsx flow still works when `REPO_TYPE=xlsx` (backward compat)
- [ ] First-run migration: detect xlsx + briefs, prompt to seed DB
- [ ] Login flow: shared password → host pick (or admin password → admin)

### Quality indicators

- [ ] No regression in Phase 1 functionality (all pages still render, briefs still load)
- [ ] All PATCH/POST operations return within 200ms on local network
- [ ] Snapshot creation takes <1s for a 1MB DB
- [ ] Note attribution is preserved across page reloads (host id in sessionStorage)
- [ ] Admin gate: non-admin users get 403 on `/api/admin/*`
- [ ] Docker compose: backend can write to mounted DB path

### User experience goals

- [ ] Incentive edit form is one click from the run page (no separate page load)
- [ ] Notes panel visible at the bottom of every run page
- [ ] Admin panel is one click from the nav (visible to admins only)
- [ ] Host identity picker is shown once per session, not on every page
- [ ] Diff badges: "Edited" indicators on incentives modified since import

### Quality (deferred tests)

Per the user's "MVP first, tests after" directive: add **lightweight smoke tests** for Phase 2 — one pytest file per major new module (`test_db.py`, `test_import_to_sqlite.py`, `test_repo_sqlite.py`, `test_admin.py`, `test_notes.py`). Aim for one test per endpoint, plus edge cases for the snapshot/restore lifecycle. Full coverage is a Phase 3 concern.

---

## 12. Implementation Phases

### Phase 2.1 — Data layer (read-only, 1-2 days)

**Goal:** SQLite-backed read path that mirrors XLSX behavior. No editing yet.

**Deliverables:**
- [ ] `src/db.py` — SQLModel engine, init
- [ ] `src/import_to_sqlite.py` — import CLI
- [ ] `web/backend/repo_sqlite.py` — read-only `SqliteIncentiveRepo`
- [ ] `web/backend/deps.py` — repo selection
- [ ] `.env.example` — `DB_PATH`, `REPO_TYPE=sqlite`
- [ ] README: how to run first import
- [ ] Smoke test: import xlsx, query via repo, compare to `XlsxIncentiveRepo` results

**Validation:** Set `REPO_TYPE=sqlite`, restart, verify marathon view shows same 176 runs + 88 incentives. Verify `check_stale()` is now based on `output/esa.db` mtime, not xlsx mtime.

### Phase 2.2 — Admin operations (1-2 days)

**Goal:** Operator can refresh, restore, view status.

**Deliverables:**
- [ ] `src/snapshot.py` — create/list/restore
- [ ] `web/backend/auth_admin.py` — admin auth (HMAC or password-in-header)
- [ ] `web/backend/routes/admin.py` — `/api/admin/*` endpoints
- [ ] `web/frontend/app/admin/page.tsx` — admin panel
- [ ] `web/frontend/lib/api_admin.ts` — admin client
- [ ] Docker compose: backend has read-write on `output/`
- [ ] README: admin password setup

**Validation:** Click "Refresh" in admin panel. Import runs. Click "Restore" on a snapshot. Verify DB rolls back. Verify non-admins get 403.

### Phase 2.3 — Incentive editing (1 day)

**Goal:** Hosts can edit incentive metadata.

**Deliverables:**
- [ ] `web/backend/routes/incentives.py` — add PATCH
- [ ] `web/frontend/components/IncentiveEditor.tsx` — inline editor
- [ ] Update `RunDetail.tsx` to use editor
- [ ] `web/frontend/lib/api.ts` — `patchIncentive()` function
- [ ] Diff endpoint for "Edited" badges

**Validation:** On run page, change incentive status from "To-Do" to "Approved". Reload. See change persisted. Check DB row.

### Phase 2.4 — Host notes (1-2 days)

**Goal:** Hosts can write attributed notes.

**Deliverables:**
- [ ] SQLModel `host` and `note` tables
- [ ] `web/backend/routes/notes.py` — notes CRUD
- [ ] Login flow: host identity picker (after shared password)
- [ ] Admin: host CRUD
- [ ] `web/frontend/components/NotesPanel.tsx`
- [ ] `web/frontend/components/HostPicker.tsx` — login step 2
- [ ] Update `RunDetail.tsx` with notes panel
- [ ] Migrate existing `<!-- HOST NOTES -->` from markdown briefs to SQLite on first v2 deploy

**Validation:** Pick "Sarah" at login. Add a note on Cuphead run. Reload — note persists with Sarah's name + timestamp. Log in as another host, see the note (read-only).

### Phase 2.5 — Polish (0.5-1 day)

**Goal:** Edge cases, error handling, smoke tests.

**Deliverables:**
- [ ] Smoke tests for each new module
- [ ] Error states: "DB locked", "Snapshot not found", "Host already exists"
- [ ] Mobile test on real device
- [ ] Update README + ADRs

**Validation:** Full workflow works on phone. Error messages are clear. No regressions.

**Total estimated effort:** 5-8 days for one developer.

---

## 13. Future Considerations

**Phase 3+ candidates:**

- **Real-time push** — websockets or SSE for live updates across multiple hosts
- **Brief generation from UI** — kick off `/brief` skill from a button, show progress
- **Per-host passwords** — proper account model, replaces shared password
- **Audit log** — track who changed what when, beyond note attribution
- **Multi-event support** — DB scoped by event_id
- **Note formatting** — markdown, mentions, links
- **Mobile PWA** — installable, offline-first
- **Slack/Discord integration** — push notes/incentive changes to a channel
- **Public summary view** — read-only mirror for donors/crew

---

## 14. Risks & Mitigations

### Locked decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Stable run identity key | Composite `(submission_id, game, category)`, stored as `run_key TEXT UNIQUE`. Falls back to `(game, category)` when submission_id missing. Slug is derived and indexed, not authoritative. | `pick` is reorderable; `scheduled` shifts. submission_id is the oengus ID — stable when oengus preserves it across re-imports. |
| Admin auth | Server-side `esa_admin_session` cookie, 1-hour expiry, set on admin login. Password in `.env` only, never shown. All admin actions logged to `output/admin_audit.log`. | HMAC is over-engineered at this scale. Cookie gives verifiable backend trust. Short expiry limits blast radius if leaked. |
| Repo swap | Direct cutover (`REPO_TYPE=xlsx` → `REPO_TYPE=sqlite` in one deploy). `REPO_TYPE=xlsx` always works as backout. | Operator is one person, fast iteration. Backout is `set env + restart`. Side-by-side `both` mode adds maintenance overhead for limited safety net. |
| Docker mount | Backend volume `:rw` (was `:ro` in Phase 1). DB writes go to `output/esa.db` and `output/snapshots/`. Briefs/xlsx still effectively read-only. | Single-mount mental model. Document the change in compose file. |

### Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| 1 | Bad import overwrites DB, losing work | Medium | High | Atomic write to temp DB then `os.replace()`. Snapshot to `output/snapshots/esa.db.{timestamp}` before every import. Rotation policy (keep last 10). Dry-run flag (`--dry-run`). Schema version check on restore. |
| 2 | Slug drift between xlsx and DB — links break | High | Medium | `run_key` is the join key (`submission_id+game+category` or `game+category`). Slug is derived for URL display, indexed for fast lookup. Existing URLs keep working because slug is stable per (game, category, scheduled). New slug only generated for genuinely new runs. |
| 3 | Concurrent edits from multiple hosts | Low | Low | SQLite serializes writes via file locking. Last-write-wins acceptable. UX nudge: detect when a row was modified since editor opened ("stale — refresh"). No optimistic locking. |
| 4 | Admin password leaked | Low | High | Server-side `esa_admin_session` cookie (not HMAC). 1-hour expiry. Password in `.env` only, never displayed. All admin actions written to `output/admin_audit.log` with timestamp + action. Rotate by editing `.env` and restarting. |
| 5 | DB file corruption on crash | Low | High | WAL mode + `synchronous=NORMAL` at DB init. `PRAGMA quick_check` on startup and every admin status call. Docker volume `:rw` (not `:ro`). Recovery: copy latest snapshot, restart. |
| 6 | Host identity confusion (reused/renamed names) | Medium | Medium | `host.id` is stable autoincrement; `host.name` is mutable. Notes denormalize `host_name` at write time — renaming doesn't rewrite history. Login confirmation step ("Sign in as Sarah?"). Soft-delete only: `is_active` flag, no cascade. |
| 7 | Frontend cache shows stale data after edit | Medium | Low | Optimistic UI (apply change immediately, revert on error). Re-fetch on `focus` and `visibilitychange` events. "Edited by X at Y" badge using row mtime. Diff endpoint deferred — not needed for v2. |
| 8 | Migration of `<!-- HOST NOTES -->` from briefs breaks | Low | Medium | Migration is opt-in: `--dry-run` by default, prints plan, exits. `--commit` to apply. Malformed blocks skipped with warning, not fatal. Manual backup of briefs before migration. |
| 9 | Phase 1 read-only flow breaks when `REPO_TYPE=sqlite` | Medium | High | Direct cutover. Backout: `REPO_TYPE=xlsx` in env + restart (always works). Smoke test in CI: assert both repos return identical data on a fixture before any `REPO_TYPE=sqlite` deploy. Schema version checked on every read. |
| 10 | Performance degradation with 1000+ notes | Low | Low | Index on `note.run_id`. Cap body at 10KB. Cap per-run notes at 100 (configurable), older auto-archived. Pagination on `/api/notes` (default 50, max 200). |

---

## 15. Appendix

### Related documents

- `docs/adr/008-host-brief-skill.md` — Phase 1 brief skill
- `docs/adr/009-web-viewer-architecture.md` — Phase 1 architecture
- `docs/adr/010-shared-password-auth.md` — Phase 1 auth model
- `docs/adr/011-repository-seam-for-incentives.md` — Phase 2 repo swap

### Key dependencies

- SQLModel: <https://sqlmodel.tiangolo.com/>
- aiosqlite: <https://github.com/omnilib/aiosqlite>
- Phase 1 stack: FastAPI 0.127, Next.js 16, Tailwind 4, React 19

### Repository structure (post-Phase 2)

```
esa-incentive-pipeline/
├── src/                          # Pipeline + brief skill
│   ├── db.py                     [new]
│   ├── import_to_sqlite.py       [new]
│   ├── snapshot.py               [new]
│   ├── brief.py
│   ├── slugs.py
│   └── ... (existing)
├── web/
│   ├── backend/
│   │   ├── repo_sqlite.py        [new]
│   │   ├── auth_admin.py         [new]
│   │   └── routes/
│   │       ├── admin.py          [new]
│   │       ├── notes.py          [new]
│   │       └── ... (existing)
│   └── frontend/
│       ├── app/admin/page.tsx    [new]
│       ├── components/
│       │   ├── IncentiveEditor.tsx [new]
│       │   ├── NotesPanel.tsx     [new]
│       │   ├── HostPicker.tsx     [new]
│       │   └── ... (existing)
│       └── lib/
│           ├── api_admin.ts      [new]
│           ├── api_notes.ts      [new]
│           └── ... (existing)
├── docs/
│   ├── PRD-phase2.md             [this file]
│   └── adr/
│       ├── 012-sqlite-data-layer.md   [new, post-implementation]
│       └── ... (existing)
├── output/                       # Now contains both xlsx + db
│   ├── incentive_plan.xlsx
│   ├── esa.db
│   ├── esa.db.snapshot-*
│   └── briefs/
└── ...
```

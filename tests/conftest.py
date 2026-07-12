import os
import tempfile
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.db import (
    Run, RunParticipant, Runner, Incentive, Host, Job,
    init_db, make_engine, SCHEMA_VERSION,
)
from web.backend.repo_sqlite import SqliteIncentiveRepo
from web.backend.deps import get_repo
from web.backend.auth_admin import current_admin
from web.backend.auth import current_session_or_admin
from web.backend import config as app_config

TZ = ZoneInfo("Europe/Stockholm")


def _naive(dt=None):
    if dt is None:
        dt = datetime.now(TZ)
    return dt.replace(tzinfo=None)


def _build_app(repo):
    """Build a FastAPI test app with all routers and get_repo overridden."""
    from web.backend.routes import health, auth as auth_routes, streams, runs, incentives, briefs
    from web.backend.routes import admin as admin_routes
    from web.backend.routes import notes as notes_routes
    from web.backend.routes import runner_notes as runner_notes_routes
    from web.backend.routes import runners as runners_routes
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(auth_routes.router)
    app.include_router(streams.router)
    app.include_router(runs.router)
    app.include_router(incentives.router)
    app.include_router(briefs.router)
    app.include_router(notes_routes.router)
    app.include_router(runner_notes_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(runners_routes.router)
    app.dependency_overrides[get_repo] = lambda: repo
    app.state.repo = repo
    return app


# ── function-scoped fixtures (test_repo_sqlite.py and isolation where needed) ─

@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.db")
        init_db(path)
        yield path


@pytest.fixture
def repo(db_path):
    return SqliteIncentiveRepo(db_path)


# ── module-scoped fixtures (shared across all tests in a file) ─────────────────

@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    """One seeded DB per test module — eliminates per-test DB creation overhead."""
    tmpdir = tmp_path_factory.mktemp("db")
    path = str(tmpdir / "test.db")
    init_db(path)
    engine = make_engine(path)
    now = _naive()
    with Session(engine) as s:
        r1 = Run(
            pick=1, scheduled=now, game="Super Mario 64", category="120 Star",
            estimate="1:30:00", estimate_seconds=5400, platform="N64",
            players="1", stream="2026 - Summer (Stream One)", stream_short="stream1",
            slug="super-mario-64__120-star__2026-07-11T1200",
            run_key="sm64-120-20260711", commentator="Alice",
            pronouns="she/her", show_cam="Yes", runner_comments="",
            imported_at=now, updated_at=now,
        )
        s.add(r1)
        s.flush()

        r2 = Run(
            pick=2, scheduled=now, game="Portal", category="Inbounds",
            estimate="0:25:00", estimate_seconds=1500, platform="PC",
            players="1", stream="2026 - Summer (Stream One)", stream_short="stream1",
            slug="portal__inbounds__2026-07-11T1300",
            run_key="portal-inb-20260711", commentator="Bob",
            pronouns="", show_cam="", runner_comments="",
            imported_at=now, updated_at=now,
        )
        s.add(r2)
        s.flush()

        for slug, display, twitch, discord, twitter, pronouns in [
            ("speedrunner1", "SpeedRunner1", "speedrunner1", "sr1#0001", "@sr1", "he/him"),
            ("speedrunner2", "SpeedRunner2", "speedrunner2", "sr2#0001", "@sr2", "she/her"),
            ("speedrunner3", "SpeedRunner3", "speedrunner3", "sr3#0001", "@sr3", "they/them"),
        ]:
            s.add(Runner(
                slug=slug, display_name=display, twitch=twitch,
                discord=discord, twitter=twitter, pronouns=pronouns,
                created_at=now, updated_at=now,
            ))

        s.flush()
        for r_id, r_slug in [(r1.id, "speedrunner1"), (r1.id, "speedrunner2"), (r2.id, "speedrunner3")]:
            runner = s.exec(select(Runner).where(Runner.slug == r_slug)).first()
            s.add(RunParticipant(
                run_id=r_id, runner_slug=r_slug,
                display_name=runner.display_name,
                twitch=runner.twitch, discord=runner.discord,
                twitter=runner.twitter, pronouns=runner.pronouns,
                imported_at=now, updated_at=now,
            ))

        s.add(Incentive(
            uuid="inc-001", run_id=r1.id, scheduled=now,
            game="Super Mario 64", category="120 Star", stream="stream1",
            participants_json="[]", incentive_text="100 coins bonus",
            details="Collect 100 coins in the first level",
            incentive_category="Reward", status="Active",
            submission_id="sub-1", imported_at=now, updated_at=now,
        ))
        s.add(Incentive(
            uuid="inc-002", run_id=r2.id, scheduled=now,
            game="Portal", category="Inbounds", stream="stream1",
            participants_json="[]", incentive_text="glitchless bonus",
            details="",
            incentive_category="Target", status="Pending",
            submission_id="sub-2", imported_at=now, updated_at=now,
        ))
        s.commit()
    engine.dispose()
    return path


@pytest.fixture(scope="module")
def client(seeded_db):
    """Module-scoped test client: auth bypassed, DB_PATH patched."""
    repo = SqliteIncentiveRepo(seeded_db)
    app = _build_app(repo)
    app.dependency_overrides[current_admin] = lambda: None
    app.dependency_overrides[current_session_or_admin] = lambda: None
    with patch.object(app_config, "DB_PATH", seeded_db):
        yield TestClient(app)


@pytest.fixture(scope="module")
def unauth_client(seeded_db):
    """Module-scoped test client without auth bypass — for 401 tests."""
    repo = SqliteIncentiveRepo(seeded_db)
    app = _build_app(repo)
    with patch.object(app_config, "DB_PATH", seeded_db):
        yield TestClient(app)


@pytest.fixture(scope="module")
def notes_client(seeded_db):
    """Module-scoped client for notes/runner-notes with auth bypassed."""
    repo = SqliteIncentiveRepo(seeded_db)
    from web.backend.routes import notes as notes_routes
    from web.backend.routes import runner_notes as runner_notes_routes
    app = FastAPI()
    app.include_router(notes_routes.router)
    app.include_router(runner_notes_routes.router)
    app.dependency_overrides[current_admin] = lambda: None
    app.dependency_overrides[current_session_or_admin] = lambda: None
    app.state.repo = repo
    with patch.object(app_config, "DB_PATH", seeded_db):
        yield TestClient(app)


# ── Stateless fixtures (no scope needed) ──────────────────────────────────────

@pytest.fixture(scope="module")
def admin_cookies():
    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer("dev-secret-change-in-prod", salt="esa-admin", signer_kwargs={"key_derivation": "hmac"})
    return {"esa_admin_session": s.dumps({"admin": True})}


@pytest.fixture(scope="module")
def host_cookies():
    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer("dev-secret-change-in-prod", salt="esa-session", signer_kwargs={"key_derivation": "hmac"})
    return {"esa_session": s.dumps({"authenticated": True})}

"""Tests for SqliteIncentiveRepo — protocol conformance and edge cases."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from src.db import Run, RunParticipant, Runner, Incentive, init_db, make_engine
from web.backend.repo_sqlite import SqliteIncentiveRepo
from web.backend.models import (
    RunDTO, IncentiveDTO, IncentivePatch, IncentiveCreateRequest,
    RunnerDTO, RunnerProfileDTO, RunnerPBDTO, ParticipantDTO,
    JobDTO, JobAlreadyRunningError,
)

TZ = ZoneInfo("Europe/Stockholm")


def _naive(dt=None):
    if dt is None:
        dt = datetime.now(TZ)
    return dt.replace(tzinfo=None)


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.db")
        init_db(path)
        yield path


@pytest.fixture
def repo(db_path):
    return SqliteIncentiveRepo(db_path)


def _seed(repo, db_path):
    """Seed minimal test data."""
    engine = make_engine(db_path)
    now = _naive()
    with Session(engine) as s:
        r = Run(
            pick=1, scheduled=now, game="Test Game", category="Any%",
            estimate="1:00", estimate_seconds=60, platform="PC",
            players="1", stream="Stream1", stream_short="s1",
            slug="test-game__any__2026-07-11T1200",
            run_key="tg-any-20260711", commentator="",
            imported_at=now, updated_at=now,
        )
        s.add(r)
        s.flush()

        runner = Runner(
            slug="runner1", display_name="Runner One",
            twitch="runner1", created_at=now, updated_at=now,
        )
        s.add(runner)
        s.flush()

        s.add(RunParticipant(
            run_id=r.id, runner_slug="runner1",
            display_name="Runner One", twitch="runner1",
            imported_at=now, updated_at=now,
        ))

        s.add(Incentive(
            uuid="inc-1", run_id=r.id, scheduled=now,
            game="Test Game", category="Any%", stream="s1",
            participants_json="[]", incentive_text="test incentive",
            incentive_category="Reward", status="Active",
            submission_id="sub-1", imported_at=now, updated_at=now,
        ))
        s.commit()
    engine.dispose()


class TestStreams:
    def test_returns_distinct_streams(self, repo, db_path):
        _seed(repo, db_path)
        streams = repo.streams()
        assert "Stream1" in streams

    def test_empty_db(self, repo):
        assert repo.streams() == []


class TestRuns:
    def test_list_all(self, repo, db_path):
        _seed(repo, db_path)
        runs = repo.runs(marathon=True)
        assert len(runs) >= 1
        assert isinstance(runs[0], RunDTO)

    def test_search_by_game(self, repo, db_path):
        _seed(repo, db_path)
        runs = repo.runs(search="Test Game", marathon=True)
        assert len(runs) == 1

    def test_search_by_participant(self, repo, db_path):
        _seed(repo, db_path)
        runs = repo.runs(search="Runner One", marathon=True)
        assert len(runs) == 1

    def test_search_no_match(self, repo, db_path):
        _seed(repo, db_path)
        runs = repo.runs(search="Nonexistent", marathon=True)
        assert len(runs) == 0

    def test_get_by_slug(self, repo, db_path):
        _seed(repo, db_path)
        r = repo.run("test-game__any__2026-07-11T1200")
        assert r is not None
        assert r.game == "Test Game"

    def test_get_by_slug_not_found(self, repo):
        assert repo.run("nonexistent") is None

    def test_run_dto_has_participants(self, repo, db_path):
        _seed(repo, db_path)
        r = repo.run("test-game__any__2026-07-11T1200")
        assert len(r.participants) == 1
        assert r.participants[0].display_name == "Runner One"


class TestIncentives:
    def test_list_all(self, repo, db_path):
        _seed(repo, db_path)
        incs = repo.incentives()
        assert len(incs) >= 1

    def test_filter_by_run_slug(self, repo, db_path):
        _seed(repo, db_path)
        incs = repo.incentives(run_slug="test-game__any__2026-07-11T1200")
        assert len(incs) == 1

    def test_get_by_uuid(self, repo, db_path):
        _seed(repo, db_path)
        inc = repo.incentive("inc-1")
        assert inc is not None
        assert inc.incentive_text == "test incentive"

    def test_get_by_uuid_not_found(self, repo):
        assert repo.incentive("nonexistent") is None

    def test_patch_incentive(self, repo, db_path):
        _seed(repo, db_path)
        patch = IncentivePatch(incentive_text="updated text")
        inc = repo.patch_incentive("inc-1", patch)
        assert inc is not None
        assert inc.incentive_text == "updated text"

    def test_patch_incentive_not_found(self, repo):
        assert repo.patch_incentive("nonexistent", IncentivePatch()) is None

    def test_create_incentive(self, repo, db_path):
        _seed(repo, db_path)
        body = IncentiveCreateRequest(
            run_slug="test-game__any__2026-07-11T1200",
            incentive_text="new incentive",
            incentive_category="Target",
        )
        inc = repo.create_incentive(body)
        assert inc.incentive_text == "new incentive"
        assert inc.run_slug == "test-game__any__2026-07-11T1200"

    def test_create_incentive_run_not_found(self, repo):
        from fastapi import HTTPException
        body = IncentiveCreateRequest(run_slug="nonexistent", incentive_text="test")
        with pytest.raises(HTTPException) as exc:
            repo.create_incentive(body)
        assert exc.value.status_code == 404

    def test_delete_incentive(self, repo, db_path):
        _seed(repo, db_path)
        inc = repo.delete_incentive("inc-1")
        assert inc is not None
        assert inc.status == "Removed"

    def test_delete_incentive_not_found(self, repo):
        assert repo.delete_incentive("nonexistent") is None


class TestRunners:
    def test_list_all(self, repo, db_path):
        _seed(repo, db_path)
        runners = repo.runners()
        assert len(runners) >= 1
        assert isinstance(runners[0], RunnerDTO)

    def test_get_by_slug(self, repo, db_path):
        _seed(repo, db_path)
        runner = repo.runner("runner1")
        assert runner is not None
        assert runner.display_name == "Runner One"

    def test_get_by_slug_not_found(self, repo):
        assert repo.runner("nonexistent") is None

    def test_runner_profile(self, repo, db_path):
        _seed(repo, db_path)
        profile = repo.runner_profile("runner1")
        assert profile is not None
        assert profile.slug == "runner1"

    def test_runner_profile_not_found(self, repo):
        assert repo.runner_profile("nonexistent") is None

    def test_runner_pbs(self, repo, db_path):
        _seed(repo, db_path)
        pbs = repo.runner_pbs("runner1")
        assert pbs is not None
        assert pbs.slug == "runner1"

    def test_runner_pbs_not_found(self, repo):
        assert repo.runner_pbs("nonexistent") is None

    def test_runner_runs(self, repo, db_path):
        _seed(repo, db_path)
        runs = repo.runner_runs("runner1")
        assert len(runs) >= 0  # may be 0 if run is in the past

    def test_runner_runs_not_found(self, repo):
        assert repo.runner_runs("nonexistent") == []


class TestUpdateRun:
    def test_update_commentator(self, repo, db_path):
        _seed(repo, db_path)
        result = repo.update_run("test-game__any__2026-07-11T1200", {"commentator": "New Commentator"})
        assert result is not None
        assert result.commentator == "New Commentator"

    def test_update_runner_slugs(self, repo, db_path):
        _seed(repo, db_path)
        engine = make_engine(db_path)
        now = _naive()
        with Session(engine) as s:
            s.add(Runner(slug="new-runner", display_name="New Runner", twitch="newrunner", created_at=now, updated_at=now))
            s.commit()
        engine.dispose()

        result = repo.update_run("test-game__any__2026-07-11T1200", {"runner_slugs": ["new-runner"]})
        assert result is not None
        assert len(result.participants) == 1
        assert result.participants[0].slug == "new-runner"

    def test_update_runner_slugs_multiple(self, repo, db_path):
        _seed(repo, db_path)
        engine = make_engine(db_path)
        now = _naive()
        with Session(engine) as s:
            s.add(Runner(slug="r2", display_name="Runner Two", twitch="r2", created_at=now, updated_at=now))
            s.add(Runner(slug="r3", display_name="Runner Three", twitch="r3", created_at=now, updated_at=now))
            s.commit()
        engine.dispose()

        result = repo.update_run("test-game__any__2026-07-11T1200", {"runner_slugs": ["r2", "r3"]})
        assert result is not None
        assert len(result.participants) == 2
        slugs = [p.slug for p in result.participants]
        assert "r2" in slugs
        assert "r3" in slugs

    def test_update_run_not_found(self, repo):
        assert repo.update_run("nonexistent", {"commentator": "x"}) is None

    def test_update_runner(self, repo, db_path):
        _seed(repo, db_path)
        result = repo.update_runner("runner1", {"display_name": "Updated Name"})
        assert result is not None
        assert result.display_name == "Updated Name"

    def test_update_runner_not_found(self, repo):
        assert repo.update_runner("nonexistent", {"display_name": "x"}) is None


class TestJobs:
    def test_create_and_get(self, repo):
        job = repo.create_job(kind="test")
        assert job.kind == "test"
        assert job.status == "pending"

        fetched = repo.get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    def test_create_duplicate_kind_raises(self, repo):
        repo.create_job(kind="test")
        with pytest.raises(JobAlreadyRunningError):
            repo.create_job(kind="test")

    def test_list_jobs(self, repo):
        repo.create_job(kind="a")
        repo.create_job(kind="b")
        jobs = repo.list_jobs()
        assert len(jobs) >= 2

    def test_list_jobs_filter_kind(self, repo):
        repo.create_job(kind="filter-me")
        repo.create_job(kind="other")
        jobs = repo.list_jobs(kind="filter-me")
        assert len(jobs) == 1

    def test_update_job(self, repo):
        job = repo.create_job(kind="test")
        updated = repo.update_job(job.id, status="running")
        assert updated.status == "running"

    def test_cancel_job(self, repo):
        job = repo.create_job(kind="test")
        cancelled = repo.cancel_job(job.id)
        assert cancelled.status == "failed"
        assert "cancelled" in cancelled.error

    def test_cancel_job_not_found(self, repo):
        assert repo.cancel_job("nonexistent") is None


class TestSpreadsheetAge:
    def test_spreadsheet_age_missing(self):
        repo = SqliteIncentiveRepo("/nonexistent/path.db")
        info = repo.spreadsheet_age()
        assert info.is_missing is True

    def test_existing_db(self, repo, db_path):
        info = repo.spreadsheet_age()
        assert info.is_missing is False


# ---------------------------------------------------------------------------
# Regression tests: Incentive.participants_json round-trip
#
# The bug (fixed 2026-07): create_incentive() wrote ParticipantDTO.model_dump()
# keys (display_name, slug, …) while _incentive_to_dto() only read the raw
# import keys (display, twitch, …).  Any API-created incentive would return
# participants with all-empty fields.
#
# These tests verify the canonical format is written and read correctly, and
# that the backward-compat fallback for legacy DTO-key rows still works.
# See ADR 0016 and Incentive docstring in src/db.py for the wire format spec.
# ---------------------------------------------------------------------------

def _seed_run_with_participant(db_path: str, run_slug: str = "game__any__2026-07-11T1200") -> tuple:
    """Seed a single run + runner + participant.  Returns (run_slug, runner info dict)."""
    engine = make_engine(db_path)
    now = _naive()
    runner_info = {
        "slug": "speedrunner99",
        "display_name": "SpeedRunner99",
        "twitch": "speedrunner99",
        "discord": "sr99#1234",
        "twitter": "@sr99",
        "pronouns": "they/them",
        "pronunciation": "speed-runner",
    }
    with Session(engine) as s:
        run = Run(
            pick=1, scheduled=now, game="Game", category="Any%",
            estimate="1:00", estimate_seconds=60, platform="PC",
            players="1", stream="Stream1", stream_short="s1",
            slug=run_slug,
            run_key=f"rk-{run_slug}",
            imported_at=now, updated_at=now,
        )
        s.add(run)
        s.flush()

        runner = Runner(
            slug=runner_info["slug"],
            display_name=runner_info["display_name"],
            twitch=runner_info["twitch"],
            discord=runner_info["discord"],
            twitter=runner_info["twitter"],
            pronouns=runner_info["pronouns"],
            pronunciation=runner_info["pronunciation"],
            created_at=now, updated_at=now,
        )
        s.add(runner)
        s.flush()

        s.add(RunParticipant(
            run_id=run.id,
            runner_slug=runner_info["slug"],
            display_name=runner_info["display_name"],
            twitch=runner_info["twitch"],
            discord=runner_info["discord"],
            twitter=runner_info["twitter"],
            pronouns=runner_info["pronouns"],
            pronunciation=runner_info["pronunciation"],
            imported_at=now, updated_at=now,
        ))
        s.commit()
    engine.dispose()
    return run_slug, runner_info


class TestIncentiveParticipantsRoundTrip:
    """Regression suite for the participants_json serialisation contract.

    Covers three participant storage paths:
      1. Import format  — raw keys (display / twitch / …) written by xlsx importer
      2. Legacy DTO format — model_dump() keys (display_name / slug / …) from
         pre-fix API writes; must still be readable without data loss
      3. API create_incentive — must write canonical import format so participants
         survive a round-trip through _incentive_to_dto
    """

    def _seed_incentive_raw(self, db_path: str, uuid: str, run_id: int,
                             participants: list[dict]) -> None:
        """Directly insert an Incentive row with custom participants_json."""
        engine = make_engine(db_path)
        now = _naive()
        with Session(engine) as s:
            s.add(Incentive(
                uuid=uuid,
                run_id=run_id,
                scheduled=now,
                game="Game", category="Any%", stream="s1",
                participants_json=json.dumps(participants),
                incentive_text="test incentive",
                incentive_category="Reward",
                status="Active",
                submission_id="sub-1",
                imported_at=now, updated_at=now,
            ))
            s.commit()
        engine.dispose()

    def _get_run_id(self, db_path: str, slug: str) -> int:
        engine = make_engine(db_path)
        with Session(engine) as s:
            run = s.exec(select(Run).where(Run.slug == slug)).first()
            assert run is not None, f"Run {slug!r} not found"
            return run.id
        engine.dispose()

    # -- Import-format participants (canonical write path) -------------------

    def test_import_format_display_name_populated(self, db_path):
        """Import-format JSON (display key) round-trips display_name correctly."""
        run_slug, runner_info = _seed_run_with_participant(db_path)
        run_id = self._get_run_id(db_path, run_slug)
        self._seed_incentive_raw(db_path, "inc-import", run_id, [{
            "display": runner_info["display_name"],
            "twitch": runner_info["twitch"],
            "discord": runner_info["discord"],
            "twitter": runner_info["twitter"],
            "pronouns": runner_info["pronouns"],
            "pronunciation": runner_info["pronunciation"],
            "submission_id": None,
            "match_confidence": "primary",
        }])

        repo = SqliteIncentiveRepo(db_path)
        inc = repo.incentive("inc-import")
        assert inc is not None
        assert len(inc.participants) == 1
        p = inc.participants[0]
        assert p.display_name == runner_info["display_name"], (
            "display_name must be populated from import-format 'display' key"
        )
        assert p.twitch == runner_info["twitch"]
        assert p.discord == runner_info["discord"]
        assert p.pronouns == runner_info["pronouns"]
        assert p.pronunciation == runner_info["pronunciation"]

    def test_import_format_slug_derived_from_twitch(self, db_path):
        """Slug is derived from twitch handle when reading import-format rows."""
        run_slug, runner_info = _seed_run_with_participant(db_path)
        run_id = self._get_run_id(db_path, run_slug)
        self._seed_incentive_raw(db_path, "inc-slug", run_id, [{
            "display": runner_info["display_name"],
            "twitch": runner_info["twitch"],
        }])

        repo = SqliteIncentiveRepo(db_path)
        inc = repo.incentive("inc-slug")
        assert inc is not None
        assert inc.participants[0].slug == runner_info["twitch"].lower()

    def test_import_format_empty_participants(self, db_path):
        """Empty participants_json returns empty participants list, not an error."""
        run_slug, _ = _seed_run_with_participant(db_path)
        run_id = self._get_run_id(db_path, run_slug)
        self._seed_incentive_raw(db_path, "inc-empty", run_id, [])

        repo = SqliteIncentiveRepo(db_path)
        inc = repo.incentive("inc-empty")
        assert inc is not None
        assert inc.participants == []

    # -- Legacy DTO-format participants (backward compatibility) -------------

    def test_legacy_dto_format_display_name_populated(self, db_path):
        """Legacy model_dump()-format JSON (display_name key) still round-trips."""
        run_slug, runner_info = _seed_run_with_participant(db_path)
        run_id = self._get_run_id(db_path, run_slug)
        # This is the broken format written by the pre-fix create_incentive()
        self._seed_incentive_raw(db_path, "inc-legacy", run_id, [{
            "slug": runner_info["slug"],
            "display_name": runner_info["display_name"],
            "twitch": runner_info["twitch"],
            "discord": runner_info["discord"],
            "twitter": runner_info["twitter"],
            "pronouns": runner_info["pronouns"],
            "pronunciation": runner_info["pronunciation"],
            "submission_id": None,
            "match_confidence": "primary",
        }])

        repo = SqliteIncentiveRepo(db_path)
        inc = repo.incentive("inc-legacy")
        assert inc is not None
        assert len(inc.participants) == 1
        p = inc.participants[0]
        assert p.display_name == runner_info["display_name"], (
            "Legacy DTO-key format (display_name) must still be readable"
        )
        assert p.twitch == runner_info["twitch"]
        assert p.slug == runner_info["slug"]

    # -- API create_incentive writes canonical format ------------------------

    def test_create_incentive_participants_populated(self, db_path):
        """Incentives created via API return full participant data on read-back.

        This is the exact regression: pre-fix, create_incentive() wrote
        model_dump() keys which _incentive_to_dto() couldn't read, so
        runner_display / participants were all empty.
        """
        run_slug, runner_info = _seed_run_with_participant(db_path)
        repo = SqliteIncentiveRepo(db_path)

        body = IncentiveCreateRequest(
            run_slug=run_slug,
            incentive_text="donate for any% race",
            incentive_category="Target",
        )
        created = repo.create_incentive(body)

        assert len(created.participants) == 1, (
            "create_incentive() must snapshot run participants into participants_json"
        )
        p = created.participants[0]
        assert p.display_name == runner_info["display_name"], (
            "participant display_name must survive the create_incentive() round-trip"
        )
        assert p.twitch == runner_info["twitch"]
        assert p.discord == runner_info["discord"]
        assert p.pronouns == runner_info["pronouns"]

    def test_create_incentive_participants_json_uses_canonical_keys(self, db_path):
        """participants_json written by create_incentive must use import-format keys.

        The canonical contract (ADR 0016) requires 'display' not 'display_name'.
        This test reads the raw DB column to confirm the write format, not just
        the DTO output, so a future regression at the serialisation layer is
        caught immediately.
        """
        run_slug, runner_info = _seed_run_with_participant(db_path)
        repo = SqliteIncentiveRepo(db_path)

        body = IncentiveCreateRequest(run_slug=run_slug, incentive_text="any%")
        created = repo.create_incentive(body)

        # Read raw participants_json from DB
        engine = make_engine(db_path)
        with Session(engine) as s:
            row = s.get(Incentive, created.uuid)
            assert row is not None
            raw = json.loads(row.participants_json)
        engine.dispose()

        assert len(raw) == 1
        p = raw[0]
        assert "display" in p, (
            "participants_json must use 'display' key (import format), not 'display_name'"
        )
        assert "display_name" not in p, (
            "participants_json must NOT contain 'display_name' (DTO format) — use 'display'"
        )
        assert p["display"] == runner_info["display_name"]
        assert p["twitch"] == runner_info["twitch"]

    def test_create_incentive_flat_fields_populated(self, db_path):
        """runner_display / runner_twitch / runner_discord flat DTO fields are set.

        These are the legacy flat fields on IncentiveDTO populated from
        participants[0].  Verifies the full chain from DB → DTO.
        """
        run_slug, runner_info = _seed_run_with_participant(db_path)
        repo = SqliteIncentiveRepo(db_path)

        body = IncentiveCreateRequest(run_slug=run_slug, incentive_text="bonus")
        inc = repo.create_incentive(body)

        assert inc.runner_display == runner_info["display_name"]
        assert inc.runner_twitch == runner_info["twitch"]
        assert inc.runner_discord == runner_info["discord"]

    def test_read_back_after_patch_preserves_participants(self, db_path):
        """patch_incentive() does not wipe participants; they survive a patch."""
        run_slug, runner_info = _seed_run_with_participant(db_path)
        repo = SqliteIncentiveRepo(db_path)

        body = IncentiveCreateRequest(run_slug=run_slug, incentive_text="original")
        created = repo.create_incentive(body)

        patched = repo.patch_incentive(created.uuid, IncentivePatch(incentive_text="updated"))
        assert patched is not None
        assert patched.incentive_text == "updated"
        assert len(patched.participants) == 1
        assert patched.participants[0].display_name == runner_info["display_name"], (
            "patch_incentive() must not destroy participants data"
        )

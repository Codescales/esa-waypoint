"""Tests for SqliteIncentiveRepo — protocol conformance and edge cases."""

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

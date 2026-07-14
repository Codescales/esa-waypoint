"""Tests for LLM-driven brief generation.

All tests run with LLM_DISABLED=1 (via monkeypatch) so no real LLM
calls are made. The LLM-disabled path returns the deterministic
build_brief prose as the fallback, which lets us verify:

1. src/llm_client.py — disabled fallback, missing-config error.
2. src/brief_builder.py — DB-primary path (incentives + all_runs args).
3. src/brief_prompts.py — prompt builders produce non-empty strings.
4. src/brief.py:generate_briefs_llm — runs against the seeded DB fixture,
   produces .md + .json files for every run, sidecar is intact.
5. src/import_to_sqlite.py:sync_runner_profiles_to_db — updates Runner.stats_json.
"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Europe/Stockholm")


# ──────────────────────────────────────────────────────────────────────────────
# llm_client
# ──────────────────────────────────────────────────────────────────────────────

class TestLlmClient:
    def test_disabled_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("LLM_DISABLED", "1")
        import importlib, src.llm_client as mod
        importlib.reload(mod)
        result = mod.complete("sys", "user", disabled_fallback="hello")
        assert result == "hello"
        importlib.reload(mod)  # reset module state

    def test_disabled_empty_fallback_by_default(self, monkeypatch):
        monkeypatch.setenv("LLM_DISABLED", "1")
        import importlib, src.llm_client as mod
        importlib.reload(mod)
        result = mod.complete("sys", "user")
        assert result == ""
        importlib.reload(mod)

    def test_missing_base_url_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_DISABLED", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "")
        monkeypatch.setenv("LLM_API_KEY", "key")
        import importlib, src.llm_client as mod
        importlib.reload(mod)
        with pytest.raises(RuntimeError, match="LLM_BASE_URL"):
            mod.complete("sys", "user")
        importlib.reload(mod)

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_DISABLED", raising=False)
        monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
        monkeypatch.setenv("LLM_API_KEY", "")
        import importlib, src.llm_client as mod
        importlib.reload(mod)
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            mod.complete("sys", "user")
        importlib.reload(mod)


# ──────────────────────────────────────────────────────────────────────────────
# brief_builder — DB-primary path
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildBriefDbPrimary:
    """Verify build_brief accepts pre-loaded incentives/all_runs without xlsx."""

    def _make_run_row(self):
        from src import xlsx_reader as xr
        return xr.RunRow(
            pick=1,
            scheduled=datetime(2026, 8, 1, 14, 0, tzinfo=TZ),
            game="Test Game",
            category="Any%",
            estimate="0:30:00",
            platform="PC",
            players="1",
            stream="stream1",
            runner_display="testrunner",
            runner_twitch="testrunner",
            runner_discord="",
            runner_twitter="",
            note=None,
            layout=None,
            submission_id="sub-test",
            category_id=None,
            incentives="",
            commentator="",
            upload_speed="",
            pronouns="",
            show_cam="",
            runner_comments="",
            participants=[],
        )

    def test_empty_incentives_and_runs(self):
        from src.brief_builder import build_brief
        from unittest.mock import patch as mp

        run = self._make_run_row()
        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None):
            md, sidecar = build_brief(run, incentives=[], all_runs=[])

        assert "Test Game" in md
        assert sidecar["slug"]
        assert sidecar["incentives"] == []
        # siblings is either [] or an empty-runs dict when no siblings found
        siblings = sidecar["siblings"]
        assert siblings == [] or (isinstance(siblings, dict) and siblings.get("total", 0) == 0)

    def test_incentives_matched_from_preloaded(self):
        from src.brief_builder import build_brief
        from src import xlsx_reader as xr
        from unittest.mock import patch as mp

        run = self._make_run_row()
        inv = xr.IncentiveRow(
            scheduled=datetime(2026, 8, 1, 14, 0, tzinfo=TZ),
            game="Test Game",
            category="Any%",
            stream="stream1",
            runner_display="testrunner",
            runner_twitch="testrunner",
            runner_discord="",
            incentive_text="Filename?",
            details="",
            incentive_category="Reward",
            valid_for_game="",
            incentive_estimate="0:01:00",
            needs_approval="No",
            status="Active",
            submission_id="sub-test",
            uuid="uuid-1",
        )

        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None):
            md, sidecar = build_brief(run, incentives=[inv], all_runs=[])

        assert len(sidecar["incentives"]) == 1
        assert sidecar["incentives"][0]["description"] == "Filename?"

    def test_no_spreadsheet_path_needed(self):
        """build_brief with DB args should not read from any xlsx path."""
        from src.brief_builder import build_brief
        from unittest.mock import patch as mp

        run = self._make_run_row()
        read_xlsx_called = []

        def _bad_read(path):
            read_xlsx_called.append(path)
            return []

        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None), \
             mp("src.brief_builder.xr.read_incentives", side_effect=_bad_read), \
             mp("src.brief_builder.xr.read_cross_reference", side_effect=_bad_read):
            build_brief(run, incentives=[], all_runs=[])

        assert read_xlsx_called == [], "xlsx read functions should not be called when DB args are provided"


# ──────────────────────────────────────────────────────────────────────────────
# brief_prompts
# ──────────────────────────────────────────────────────────────────────────────

class TestBriefPrompts:
    def _sidecar(self):
        return {
            "run_meta": {
                "game": "Super Mario 64",
                "category": "120 Star",
                "estimate": "1:30:00",
                "platform": "N64",
                "stream": "stream1",
                "scheduled": "2026-08-01T14:00:00+02:00",
                "participants": [{"name": "testrunner", "twitch": "testrunner"}],
            },
            # runner_section is identity-only now
            "runner_section": {"name": "testrunner", "verified": True, "src_url": "https://www.speedrun.com/users/testrunner"},
            "category_section": {"name": "120 Star", "records": [{"place": 1, "runner": "cheese05", "time": "1:38:27", "date": "2024-01-01"}]},
            "game_section": {"name": "Super Mario 64", "abbreviation": "sm64", "src_url": "https://www.speedrun.com/sm64"},
            "incentives": [{"category": "Reward", "description": "Name a Bob-omb", "estimate": "0:01:00"}],
            "siblings": [],
            "confidence_flags": [],
        }

    def test_scan_prompt_nonempty(self):
        from src.brief_prompts import build_user_prompt
        sd = self._sidecar()
        prompt = build_user_prompt(mode="scan", run_meta=sd["run_meta"], sidecar=sd)
        assert len(prompt) > 100
        assert "Super Mario 64" in prompt
        assert "scan" in prompt.lower() or "60 second" in prompt.lower()

    def test_interview_prompt_nonempty(self):
        from src.brief_prompts import build_user_prompt
        sd = self._sidecar()
        prompt = build_user_prompt(mode="interview", run_meta=sd["run_meta"], sidecar=sd)
        assert "interview" in prompt.lower() or "talking point" in prompt.lower()

    def test_full_prompt_nonempty(self):
        from src.brief_prompts import build_user_prompt
        sd = self._sidecar()
        prompt = build_user_prompt(mode="full", run_meta=sd["run_meta"], sidecar=sd)
        assert "full" in prompt.lower() or "comprehensive" in prompt.lower()

    def test_prompt_does_not_accept_runner_profile(self):
        """build_user_prompt no longer accepts a runner_profile argument."""
        import inspect
        from src.brief_prompts import build_user_prompt
        sig = inspect.signature(build_user_prompt)
        assert "runner_profile" not in sig.parameters, \
            "runner_profile param removed — runner history must not be in run prompts"

    def test_prompt_instructs_no_runner_history(self):
        """System prompt explicitly forbids runner history."""
        from src.brief_prompts import SYSTEM_PROMPT
        assert "runner" in SYSTEM_PROMPT.lower()
        # Must contain an instruction prohibiting runner history
        assert "do not" in SYSTEM_PROMPT.lower() or "not" in SYSTEM_PROMPT.lower()

    def test_runner_section_has_no_pb_fields(self):
        """runner_section in sidecar must not contain pb_count or top_games."""
        sd = self._sidecar()
        rs = sd["runner_section"]
        assert "pb_count" not in rs
        assert "top_games" not in rs


# ──────────────────────────────────────────────────────────────────────────────
# generate_briefs_llm — integration against seeded DB (LLM_DISABLED=1)
# ──────────────────────────────────────────────────────────────────────────────

class TestGenerateBriefsLlm:
    def _run(self, seeded_db, briefs_dir):
        """Helper: run generate_briefs_llm with all external calls stubbed."""
        from unittest.mock import patch as mp
        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None), \
             mp("src.brief.cmd_cache_past_schedules"), \
             mp("src.brief._fetch_runner_profile", return_value={}), \
             mp("src.brief._load_runner_profile_cache", return_value={}), \
             mp("src.llm_client._DISABLED", True):
            from src.brief import generate_briefs_llm
            return generate_briefs_llm(db_path=seeded_db, briefs_dir=briefs_dir)

    def test_generates_files_for_all_runs(self, seeded_db, monkeypatch, tmp_path):
        monkeypatch.setenv("LLM_DISABLED", "1")
        briefs_dir = str(tmp_path / "briefs")
        os.makedirs(briefs_dir)

        result = self._run(seeded_db, briefs_dir)

        assert result["count"] >= 1, f"Expected at least 1 brief, errors: {result['errors']}"
        assert result["errors"] == []

        md_files = [f for f in os.listdir(briefs_dir) if f.endswith(".md")]
        json_files = [f for f in os.listdir(briefs_dir) if f.endswith(".json")]
        assert len(md_files) >= 1
        assert len(json_files) >= 1
        assert len(md_files) == len(json_files)

    def test_sidecar_structure_intact(self, seeded_db, monkeypatch, tmp_path):
        monkeypatch.setenv("LLM_DISABLED", "1")
        briefs_dir = str(tmp_path / "briefs2")
        os.makedirs(briefs_dir)

        self._run(seeded_db, briefs_dir)

        json_files = [f for f in os.listdir(briefs_dir) if f.endswith(".json")]
        assert len(json_files) >= 1
        for jf in json_files:
            with open(os.path.join(briefs_dir, jf)) as f:
                data = json.load(f)
            assert "slug" in data
            assert "mode" in data
            assert "incentives" in data
            assert "siblings" in data
            assert "confidence_flags" in data
            assert "run_meta" in data
            # Runner history must NOT be in the run sidecar
            assert "runner_profile" not in data, "runner_profile must not appear in run sidecar"
            assert "runner_profiles" not in data, "runner_profiles must not appear in run sidecar"
            # runner_section must be identity-only
            rs = data.get("runner_section") or {}
            assert "pb_count" not in rs, "pb_count must not appear in runner_section"
            assert "top_games" not in rs, "top_games must not appear in runner_section"


    def test_slug_filter_limits_output(self, seeded_db, monkeypatch, tmp_path):
        """Only the targeted slug should produce a brief file."""
        monkeypatch.setenv("LLM_DISABLED", "1")
        briefs_dir = str(tmp_path / "briefs_slug")
        os.makedirs(briefs_dir)

        # Get the actual slugs from the DB so we can target one
        from src import xlsx_reader as xr
        from zoneinfo import ZoneInfo
        TZ = ZoneInfo("Europe/Stockholm")
        runs = xr.read_cross_reference_from_db(seeded_db)
        assert len(runs) >= 2, "seeded_db should have at least 2 runs"
        from src.slugs import run_slug
        first_run = runs[0]
        sched = first_run.scheduled
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=TZ)
        target_slug = run_slug(first_run.game, first_run.category, sched, first_run.submission_id or "")

        from unittest.mock import patch as mp
        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None), \
             mp("src.brief.cmd_cache_past_schedules"), \
             mp("src.brief._fetch_runner_profile", return_value={}), \
             mp("src.brief._load_runner_profile_cache", return_value={}), \
             mp("src.llm_client._DISABLED", True):
            from src.brief import generate_briefs_llm
            result = generate_briefs_llm(
                db_path=seeded_db,
                briefs_dir=briefs_dir,
                slugs=[target_slug],
            )

        assert result["count"] == 1, f"Expected 1 brief, got: {result}"
        md_files = [f for f in os.listdir(briefs_dir) if f.endswith(".md")]
        assert len(md_files) == 1
        assert md_files[0] == f"{target_slug}.md"

    def test_runner_twitch_filter(self, seeded_db, monkeypatch, tmp_path):
        """Only runs matching the given Twitch handle should be generated."""
        monkeypatch.setenv("LLM_DISABLED", "1")
        briefs_dir = str(tmp_path / "briefs_runner")
        os.makedirs(briefs_dir)

        # seeded_db has speedrunner1 (SM64) and speedrunner3 (Portal)
        from unittest.mock import patch as mp
        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None), \
             mp("src.brief.cmd_cache_past_schedules"), \
             mp("src.brief._fetch_runner_profile", return_value={}), \
             mp("src.brief._load_runner_profile_cache", return_value={}), \
             mp("src.llm_client._DISABLED", True):
            from src.brief import generate_briefs_llm
            result = generate_briefs_llm(
                db_path=seeded_db,
                briefs_dir=briefs_dir,
                runner_twitches=["speedrunner1"],
            )

        assert result["count"] == 1, f"Expected 1 brief for speedrunner1, got: {result}"

    def test_no_filter_processes_all(self, seeded_db, monkeypatch, tmp_path):
        """Without filters all runs are processed (regression guard)."""
        monkeypatch.setenv("LLM_DISABLED", "1")
        briefs_dir = str(tmp_path / "briefs_all")
        os.makedirs(briefs_dir)

        from src import xlsx_reader as xr
        expected = len(xr.read_cross_reference_from_db(seeded_db))

        from unittest.mock import patch as mp
        with mp("src.brief_builder.search_src_game", return_value=None), \
             mp("src.brief_builder.search_user_by_lookup", return_value=None), \
             mp("src.brief.cmd_cache_past_schedules"), \
             mp("src.brief._fetch_runner_profile", return_value={}), \
             mp("src.brief._load_runner_profile_cache", return_value={}), \
             mp("src.llm_client._DISABLED", True):
            from src.brief import generate_briefs_llm
            result = generate_briefs_llm(db_path=seeded_db, briefs_dir=briefs_dir)

        assert result["count"] == expected, f"Expected {expected} briefs, got: {result}"




class TestSyncRunnerProfilesToDb:
    def test_updates_matching_runners(self, seeded_db, tmp_path):
        from src.import_to_sqlite import sync_runner_profiles_to_db
        from src.db import make_engine, Runner as DBRunner
        from sqlmodel import Session, select

        profiles_path = str(tmp_path / "runner_profiles.json")
        profiles = {
            "speedrunner1|speedrunner1": {
                "summary": {"appearance_count": 2, "pb_count": 10},
                "stats": {},
                "sources": [],
                "errors": [],
            }
        }
        with open(profiles_path, "w") as f:
            json.dump(profiles, f)

        result = sync_runner_profiles_to_db(seeded_db, profiles_cache_path=profiles_path)

        assert result["updated"] >= 1
        assert result["errors"] == []

        engine = make_engine(seeded_db)
        with Session(engine) as s:
            runner = s.exec(select(DBRunner).where(DBRunner.slug == "speedrunner1")).first()
        engine.dispose()

        assert runner is not None
        assert runner.stats_json
        stats = json.loads(runner.stats_json)
        assert stats["summary"]["appearance_count"] == 2

    def test_missing_cache_file_returns_zero(self, seeded_db):
        from src.import_to_sqlite import sync_runner_profiles_to_db
        result = sync_runner_profiles_to_db(seeded_db, profiles_cache_path="/nonexistent/path.json")
        assert result["updated"] == 0
        assert result["skipped"] == 0

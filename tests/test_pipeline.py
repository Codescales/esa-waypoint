import os
import tempfile
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock, mock_open

from src.pipeline import (
    _load_dotenv,
    run_pipeline,
    _tiltify_push_main,
    _tiltify_login_main,
    _load_tiltify_session,
    _save_token_to_env,
    _write_csv,
    _add_tiltify_args,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestLoadDotenv:
    def test_no_env_file(self):
        _load_dotenv()

    def test_with_env_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w") as f:
                f.write("TEST_KEY=test_value\n")
            with patch("src.pipeline.os.path.dirname", return_value=tmpdir), \
                 patch("src.pipeline.os.path.exists", return_value=True), \
                 patch("builtins.open", return_value=open(env_path)):
                _load_dotenv()
                assert os.environ.get("TEST_KEY") == "test_value"
                del os.environ["TEST_KEY"]

    def test_skips_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w") as f:
                f.write("# comment\nKEY=val\n")
            with patch("src.pipeline.os.path.dirname", return_value=tmpdir), \
                 patch("src.pipeline.os.path.exists", return_value=True), \
                 patch("builtins.open", return_value=open(env_path)):
                _load_dotenv()
                assert os.environ.get("KEY") == "val"
                del os.environ["KEY"]

    def test_skips_malformed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w") as f:
                f.write("MALFORMED\n")
            with patch("src.pipeline.os.path.dirname", return_value=tmpdir), \
                 patch("src.pipeline.os.path.exists", return_value=True), \
                 patch("builtins.open", return_value=open(env_path)):
                _load_dotenv()

    def test_does_not_override_existing(self):
        os.environ["EXISTING_KEY"] = "original"
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w") as f:
                f.write("EXISTING_KEY=override\n")
            with patch("src.pipeline.os.path.dirname", return_value=tmpdir), \
                 patch("src.pipeline.os.path.exists", return_value=True), \
                 patch("builtins.open", return_value=open(env_path)):
                _load_dotenv()
                assert os.environ["EXISTING_KEY"] == "original"
        del os.environ["EXISTING_KEY"]


class TestSaveTokenToEnv:
    def test_saves_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w") as f:
                f.write("OTHER=val\n")
            with patch("src.pipeline.os.path.dirname") as mock_dirname:
                mock_dirname.return_value = tmpdir
                with patch("src.pipeline.os.path.exists", return_value=True):
                    _save_token_to_env("test-token")
            content = open(env_path).read()
            assert "OENGUS_TOKEN=test-token" in content


class TestWriteCsv:
    def test_writes_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.csv")
            from src.horaro import ScheduleItem
            items = [ScheduleItem(
                game="Test", players="", platform="PC", category="Any%",
                note=None, layout=None, submission_id=None, category_id=None,
                estimate_seconds=1800,
                scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
                setup_seconds=0, stream="s1",
            )]
            marathon = type("M", (), {"name": "Test Marathon", "submissions": []})()
            _write_csv(items, marathon, path)
            assert os.path.exists(path)
            content = open(path).read()
            assert "Test" in content


class TestAddTiltifyArgs:
    def test_adds_args(self):
        import argparse
        parser = argparse.ArgumentParser()
        _add_tiltify_args(parser)
        args = parser.parse_args([])
        assert hasattr(args, "tiltify_push")
        assert hasattr(args, "tiltify_dry_run")
        assert hasattr(args, "tiltify_campaign_id")
        assert hasattr(args, "tiltify_session")
        assert hasattr(args, "tiltify_cookie")
        assert hasattr(args, "incentive_dollar_per_minute")
        assert hasattr(args, "tiltify_keep_going")


class TestLoadTiltifySession:
    def test_no_session(self):
        args = type("A", (), {"tiltify_session": None, "tiltify_cookie": None})()
        result = _load_tiltify_session(args)
        assert result is None

    def test_with_cookie(self):
        args = type("A", (), {
            "tiltify_session": None,
            "tiltify_cookie": "_tiltify_session_key_v7=abc123",
        })()
        result = _load_tiltify_session(args)
        assert result is not None

    def test_with_session_path(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "cookies": [{"name": "_tiltify_session_key_v7", "value": "abc"}],
                "origins": [],
            }, f)
            path = f.name
        try:
            args = type("A", (), {"tiltify_session": path, "tiltify_cookie": None})()
            result = _load_tiltify_session(args)
            assert result is not None
        finally:
            os.unlink(path)


class TestTiltifyPushMain:
    def test_no_session(self):
        args = type("A", (), {
            "tiltify_push": True,
            "tiltify_dry_run": False,
            "tiltify_campaign_id": "camp-1",
            "tiltify_session": None,
            "tiltify_cookie": None,
            "output": "test.xlsx",
            "incentive_dollar_per_minute": 5.0,
            "tiltify_keep_going": False,
            "source": "xlsx",
            "db_path": "output/esa.db",
            "tiltify_headless": "true",
            "tiltify_max": 0,
        })()
        with patch("src.pipeline._load_tiltify_session", return_value=None):
            result = _tiltify_push_main(args)
            assert result == 1

    def test_dry_run_no_xlsx(self):
        args = type("A", (), {
            "tiltify_push": True,
            "tiltify_dry_run": True,
            "tiltify_campaign_id": "camp-1",
            "tiltify_session": None,
            "tiltify_cookie": "_tiltify_session_key_v7=abc",
            "output": "/nonexistent.xlsx",
            "incentive_dollar_per_minute": 5.0,
            "tiltify_keep_going": False,
            "source": "xlsx",
            "db_path": "output/esa.db",
            "tiltify_headless": "true",
            "tiltify_max": 0,
        })()
        result = _tiltify_push_main(args)
        assert result == 1


class TestTiltifyLoginMain:
    def test_no_playwright(self):
        args = type("A", (), {
            "tiltify_session": "output/tiltify_session.json",
            "tiltify_cookie": None,
        })()
        import builtins
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "playwright":
                raise ImportError("no playwright")
            return original_import(name, *args, **kwargs)
        with patch.object(builtins, "__import__", mock_import):
            result = _tiltify_login_main(args)
            assert result == 1


class TestRunPipeline:
    pass

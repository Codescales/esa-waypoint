import os
import tempfile
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock, mock_open

from src.tiltify import (
    CreateRewardRequest,
    CreatePollRequest,
    CreateTargetRequest,
    ExistingReward,
    StubTiltifyClient,
    TiltifySession,
    TiltifySessionError,
    _parse_amount_cents,
    _format_amount,
    _css_escape,
    parse_cookie_header_as_storage_state,
    iter_session_files,
    save_session_from_console_cookies,
    TiltifyClient,
    PlaywrightTiltifyClient,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestCreateRewardRequest:
    def test_fields(self):
        req = CreateRewardRequest(name="Test", amount_cents=1000, description="Desc")
        assert req.name == "Test"
        assert req.amount_cents == 1000
        assert req.description == "Desc"


class TestCreatePollRequest:
    def test_fields(self):
        req = CreatePollRequest(name="Poll", options=["A", "B"])
        assert req.name == "Poll"
        assert req.options == ["A", "B"]


class TestCreateTargetRequest:
    def test_fields(self):
        req = CreateTargetRequest(name="Target", amount_cents=5000)
        assert req.name == "Target"
        assert req.amount_cents == 5000


class TestExistingReward:
    def test_fields(self):
        r = ExistingReward(reward_id="r1", name="Test", amount_cents=1000)
        assert r.reward_id == "r1"
        assert r.name == "Test"
        assert r.amount_cents == 1000


class TestStubTiltifyClient:
    def test_create_reward(self):
        client = StubTiltifyClient()
        req = CreateRewardRequest(name="Test", amount_cents=1000, description="Desc")
        rid = client.create_reward(req)
        assert rid is not None
        assert len(client.calls) == 1

    def test_create_poll(self):
        client = StubTiltifyClient()
        req = CreatePollRequest(name="Poll", options=["A", "B"])
        pid = client.create_poll(req)
        assert pid is not None
        assert len(client.calls) == 1

    def test_create_target(self):
        client = StubTiltifyClient()
        req = CreateTargetRequest(name="Target", amount_cents=5000)
        tid = client.create_target(req)
        assert tid is not None
        assert len(client.calls) == 1

    def test_list_rewards(self):
        existing = [
            ExistingReward(reward_id="r1", name="R1", amount_cents=1000),
            ExistingReward(reward_id="r2", name="R2", amount_cents=2000),
        ]
        client = StubTiltifyClient(existing_rewards=existing)
        rewards = client.list_rewards()
        assert len(rewards) == 2

    def test_close(self):
        client = StubTiltifyClient()
        client.close()


class TestTiltifySession:
    def test_from_storage_state_missing_file(self):
        with pytest.raises(TiltifySessionError, match="not found"):
            TiltifySession.from_storage_state("/nonexistent/file.json")

    def test_from_storage_state_invalid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            with pytest.raises(TiltifySessionError, match="Invalid session JSON"):
                TiltifySession.from_storage_state(path)
        finally:
            os.unlink(path)

    def test_from_storage_state_missing_keys(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"some": "data"}, f)
            path = f.name
        try:
            with pytest.raises(TiltifySessionError, match="not a Playwright storage_state"):
                TiltifySession.from_storage_state(path)
        finally:
            os.unlink(path)

    def test_from_storage_state_missing_session_cookie(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({"cookies": [{"name": "other", "value": "x"}], "origins": []}, f)
            path = f.name
        try:
            with pytest.raises(TiltifySessionError, match="missing the auth cookie"):
                TiltifySession.from_storage_state(path)
        finally:
            os.unlink(path)

    def test_from_storage_state_valid(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "cookies": [{"name": "_tiltify_session_key_v7", "value": "abc"}],
                "origins": [],
            }, f)
            path = f.name
        try:
            session = TiltifySession.from_storage_state(path)
            assert session is not None
            assert session.url == "https://app.tiltify.com"
        finally:
            os.unlink(path)

    def test_from_cookie_header_empty(self):
        with pytest.raises(TiltifySessionError, match="Empty"):
            TiltifySession.from_cookie_header("")

    def test_from_cookie_header_missing_session(self):
        with pytest.raises(TiltifySessionError, match="missing"):
            TiltifySession.from_cookie_header("other=value")

    def test_from_cookie_header_valid(self):
        session = TiltifySession.from_cookie_header("_tiltify_session_key_v7=abc123")
        assert session is not None
        assert len(session.storage_state["cookies"]) == 1
        assert session.storage_state["cookies"][0]["name"] == "_tiltify_session_key_v7"

    def test_from_cookie_header_skips_malformed_parts(self):
        session = TiltifySession.from_cookie_header("_tiltify_session_key_v7=abc; =val; justname")
        assert session is not None
        assert len(session.storage_state["cookies"]) == 1


class TestParseAmountCents:
    def test_dollar_format(self):
        assert _parse_amount_cents("$10.00") == 1000

    def test_no_dollar_sign(self):
        assert _parse_amount_cents("10.00") == 1000

    def test_integer(self):
        assert _parse_amount_cents("$5") == 500

    def test_empty(self):
        assert _parse_amount_cents("") is None

    def test_invalid(self):
        assert _parse_amount_cents("abc") is None

    def test_euro_format(self):
        assert _parse_amount_cents("10,50") == 105000


class TestFormatAmount:
    def test_basic(self):
        assert _format_amount(1000) == "10.00"

    def test_zero(self):
        assert _format_amount(0) == "0.00"

    def test_small(self):
        assert _format_amount(50) == "0.50"


class TestCssEscape:
    def test_quotes(self):
        escaped = _css_escape('hello"world')
        assert '\\"' in escaped

    def test_backslash(self):
        escaped = _css_escape("test\\path")
        assert "\\\\" in escaped or escaped == "test\\\\path"

    def test_no_special(self):
        assert _css_escape("hello") == "hello"


class TestParseCookieHeaderAsStorageState:
    def test_basic(self):
        header = "_tiltify_session_key_v7=abc123; token=xyz"
        result = parse_cookie_header_as_storage_state(header)
        assert "cookies" in result
        assert len(result["cookies"]) > 0


class TestIterSessionFiles:
    def test_no_valid_paths(self):
        result = iter_session_files(["/nonexistent1", "/nonexistent2"])
        assert result is None

    def test_skips_empty(self):
        result = iter_session_files(["", None])
        assert result is None

    def test_first_valid_wins(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({
                "cookies": [{"name": "_tiltify_session_key_v7", "value": "abc"}],
                "origins": [],
            }, f)
            path = f.name
        try:
            result = iter_session_files(["/nonexistent", path])
            assert result is not None
        finally:
            os.unlink(path)


class TestSaveSessionFromConsoleCookies:
    def test_saves_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            save_session_from_console_cookies(path, {"cookies": [{"name": "test", "value": "x"}]})
            assert os.path.exists(path)
            data = json.load(open(path))
            assert "cookies" in data

    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "session.json")
            save_session_from_console_cookies(path, {"cookies": []})
            assert os.path.exists(path)


class TestTiltifyClientProtocol:
    def test_is_protocol(self):
        import typing
        assert typing.is_protocol(TiltifyClient)


class TestPlaywrightTiltifyClient:
    def test_requires_session(self):
        with pytest.raises(TypeError):
            PlaywrightTiltifyClient()


import pytest

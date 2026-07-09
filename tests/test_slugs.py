from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from src.slugs import (
    _is_cjk,
    _slugify,
    game_slug,
    category_slug,
    run_slug,
    stream_token,
    runner_slug,
    time_token,
    shift_dir_slug,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestIsCjk:
    def test_cjk_chinese(self):
        assert _is_cjk("中文游戏")

    def test_cjk_japanese(self):
        assert _is_cjk("ゲーム")

    def test_cjk_korean(self):
        assert _is_cjk("게임")

    def test_ascii(self):
        assert not _is_cjk("Hello World")

    def test_mixed(self):
        assert _is_cjk("Hello 中文")


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _slugify("Donkey Kong 64") == "donkey-kong-64"

    def test_unicode_normalization(self):
        assert _slugify("Pokémon") == "pokemon"

    def test_empty_returns_untitled(self):
        assert _slugify("") == "untitled"

    def test_max_length(self):
        long = "a" * 100
        result = _slugify(long, max_length=20)
        assert len(result) <= 20

    def test_trailing_hyphen_trimmed(self):
        result = _slugify("hello-", max_length=5)
        assert not result.endswith("-")


class TestGameSlug:
    def test_normal(self):
        assert game_slug("Super Mario 64") == "super-mario-64"

    def test_cjk_fallback(self):
        assert game_slug("中文游戏", "42") == "run-42"

    def test_cjk_no_submission_id(self):
        assert game_slug("中文游戏") == "run"

    def test_empty(self):
        assert game_slug("") == "run"


class TestCategorySlug:
    def test_normal(self):
        assert category_slug("Any%") == "any"

    def test_empty(self):
        assert category_slug("") == "uncategorized"


class TestRunSlug:
    def test_basic(self):
        dt = datetime(2026, 8, 1, 14, 30, 0, tzinfo=TZ)
        result = run_slug("Super Mario 64", "Any%", dt, "123")
        assert "super-mario-64" in result
        assert "any" in result
        assert "2026-08-01T1430" in result or "2026-08-01T1400" in result


class TestStreamToken:
    def test_stream_one(self):
        assert stream_token("2026 - Summer (Stream One)") == "stream1"

    def test_stream_two(self):
        assert stream_token("2026 - Summer (Stream Two)") == "stream2"

    def test_stream_three(self):
        assert stream_token("2026 - Summer (Stream Three)") == "stream3"

    def test_no_season_prefix(self):
        assert stream_token("Horaro stream") == "horaro-stream"

    def test_empty(self):
        assert stream_token("") == "untitled"


class TestRunnerSlug:
    def test_twitch_present(self):
        assert runner_slug("SomeTwitch", "Display Name", 1) == "sometwitch"

    def test_twitch_empty_display_present(self):
        result = runner_slug("", "Display Name", 42)
        assert result.startswith("player-")
        assert "42" in result

    def test_both_empty(self):
        assert runner_slug("", "", 7) == "player-unknown-7"


class TestTimeToken:
    def test_floors_to_hour(self):
        dt = datetime(2026, 8, 1, 14, 22, 0, tzinfo=TZ)
        assert time_token(dt) == "1400"

    def test_exact_hour(self):
        dt = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        assert time_token(dt) == "1400"


class TestShiftDirSlug:
    def test_basic(self):
        start = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        end = datetime(2026, 8, 1, 16, 0, 0, tzinfo=TZ)
        result = shift_dir_slug(start, end)
        assert "2026-08-01" in result
        assert "1400" in result
        assert "1600" in result

    def test_with_stream(self):
        start = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        end = datetime(2026, 8, 1, 16, 0, 0, tzinfo=TZ)
        result = shift_dir_slug(start, end, "2026 - Summer (Stream One)")
        assert result.endswith("_stream1")

    def test_end_before_start(self):
        start = datetime(2026, 8, 1, 16, 0, 0, tzinfo=TZ)
        end = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        result = shift_dir_slug(start, end)
        assert "1600-1600" in result

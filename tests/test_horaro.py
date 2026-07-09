from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from src.horaro import (
    ScheduleItem,
    Schedule,
    parse_iso_duration,
    parse_horaro_datetime,
    list_event_schedules,
    fetch_schedule_raw,
    match_runner_in_items,
    fetch_schedule,
    _norm_col,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestParseIsoDuration:
    def test_hours_minutes_seconds(self):
        assert parse_iso_duration("PT1H30M15S") == 5415

    def test_hours_minutes(self):
        assert parse_iso_duration("PT1H30M") == 5400

    def test_minutes_only(self):
        assert parse_iso_duration("PT35M") == 2100

    def test_seconds_only(self):
        assert parse_iso_duration("PT12S") == 12

    def test_empty(self):
        assert parse_iso_duration("") == 0

    def test_no_match(self):
        assert parse_iso_duration("invalid") == 0


class TestParseHoraroDatetime:
    def test_with_timezone(self):
        dt = parse_horaro_datetime("2026-08-01T14:00:00+02:00")
        assert dt.year == 2026
        assert dt.month == 8
        assert dt.hour == 14


class TestScheduleItem:
    def test_estimate_str_hours(self):
        item = ScheduleItem(
            game="Test", players="", platform="", category="", note=None, layout=None,
            submission_id=None, category_id=None, estimate_seconds=3661,
            scheduled=datetime(2026, 1, 1, tzinfo=TZ), setup_seconds=0, stream="s1",
        )
        assert item.estimate_str == "01:01:01"

    def test_estimate_str_minutes(self):
        item = ScheduleItem(
            game="Test", players="", platform="", category="", note=None, layout=None,
            submission_id=None, category_id=None, estimate_seconds=1830,
            scheduled=datetime(2026, 1, 1, tzinfo=TZ), setup_seconds=0, stream="s1",
        )
        assert item.estimate_str == "30:30"

    def test_runner_names_from_markdown(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.runner_names == ["Runner1"]

    def test_runner_names_plain_text(self):
        item = ScheduleItem(
            game="Test", players="Runner1, Runner2", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.runner_names == ["Runner1, Runner2"]

    def test_runner_twitch(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.runner_twitch == ["r1"]

    def test_participants_from_markdown(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        parts = item.participants
        assert len(parts) == 1
        assert parts[0]["display"] == "Runner1"
        assert parts[0]["twitch"] == "r1"

    def test_participants_plain_text(self):
        item = ScheduleItem(
            game="Test", players="Runner1, Runner2", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        parts = item.participants
        assert len(parts) == 2
        assert parts[0]["display"] == "Runner1"

    def test_participants_empty(self):
        item = ScheduleItem(
            game="Test", players="", platform="", category="", note=None, layout=None,
            submission_id=None, category_id=None, estimate_seconds=0,
            scheduled=datetime(2026, 1, 1, tzinfo=TZ), setup_seconds=0, stream="s1",
        )
        assert item.participants == []

    def test_is_multi_player(self):
        item = ScheduleItem(
            game="Test", players="[A](https://twitch.tv/a), [B](https://twitch.tv/b)",
            platform="", category="", note=None, layout=None, submission_id=None,
            category_id=None, estimate_seconds=0,
            scheduled=datetime(2026, 1, 1, tzinfo=TZ), setup_seconds=0, stream="s1",
        )
        assert item.is_multi_player is True

    def test_not_multi_player(self):
        item = ScheduleItem(
            game="Test", players="[A](https://twitch.tv/a)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.is_multi_player is False

    def test_mentions_runner_by_name(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("Runner1") is True

    def test_mentions_runner_by_twitch(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("", "r1") is True

    def test_mentions_runner_no_match(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("Nobody") is False

    def test_mentions_runner_empty(self):
        item = ScheduleItem(
            game="Test", players="", platform="", category="", note=None, layout=None,
            submission_id=None, category_id=None, estimate_seconds=0,
            scheduled=datetime(2026, 1, 1, tzinfo=TZ), setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("", "") is False

    def test_mentions_runner_plain_text(self):
        item = ScheduleItem(
            game="Test", players="Runner1, Runner2", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("Runner1") is True

    def test_mentions_runner_twitch_in_players(self):
        item = ScheduleItem(
            game="Test", players="[Runner1](https://twitch.tv/r1)", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("", "r1") is True

    def test_mentions_runner_word_boundary(self):
        item = ScheduleItem(
            game="Test", players="An, Nathan", platform="",
            category="", note=None, layout=None, submission_id=None, category_id=None,
            estimate_seconds=0, scheduled=datetime(2026, 1, 1, tzinfo=TZ),
            setup_seconds=0, stream="s1",
        )
        assert item.mentions_runner("An") is True
        assert item.mentions_runner("Nathan") is True


class TestNormCol:
    def test_basic(self):
        assert _norm_col("Game") == "game"

    def test_with_spaces(self):
        assert _norm_col("Players / Runners") == "players___runners"

    def test_with_parens(self):
        assert _norm_col("Setup (sec)") == "setup_sec"

    def test_empty(self):
        assert _norm_col("") == ""


class TestMatchRunnerInItems:
    def test_match_by_name(self):
        items = [{"data": ["Game1", "[Runner1](https://twitch.tv/r1)"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "Runner1")
        assert len(result) == 1
        assert result[0]["match"] == "name"

    def test_match_by_twitch(self):
        items = [{"data": ["Game1", "[Runner1](https://twitch.tv/r1)"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "", "r1")
        assert len(result) == 1
        assert result[0]["match"] == "twitch"

    def test_no_match(self):
        items = [{"data": ["Game1", "[Runner1](https://twitch.tv/r1)"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "Nobody")
        assert len(result) == 0

    def test_empty_name_and_twitch(self):
        items = [{"data": ["Game1", "Runner1"]}]
        col_map = {"game": 0, "players": 1}
        assert match_runner_in_items(items, col_map, "", "") == []

    def test_no_player_column(self):
        items = [{"data": ["Game1"]}]
        col_map = {"game": 0}
        result = match_runner_in_items(items, col_map, "Runner1")
        assert len(result) == 0

    def test_match_plain_text(self):
        items = [{"data": ["Game1", "Runner1"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "Runner1")
        assert len(result) == 1

    def test_match_by_twitch_in_players_cell(self):
        items = [{"data": ["Game1", "[Runner1](https://twitch.tv/r1)"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "", "r1")
        assert len(result) == 1
        assert result[0]["match"] == "twitch"

    def test_player_idx_out_of_range(self):
        items = [{"data": ["Game1"]}]
        col_map = {"game": 0, "players": 1}
        result = match_runner_in_items(items, col_map, "Runner1")
        assert len(result) == 0


class TestListEventSchedules:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"slug": "s1", "name": "Schedule 1", "start": "2026-01-01", "id": "1"},
                {"slug": "s2", "name": "Schedule 2", "start": "2026-02-01", "id": "2"},
            ]
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = list_event_schedules("testorg")
            assert len(result) == 2
            assert result[0]["slug"] == "s1"

    def test_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = list_event_schedules("testorg")
            assert result == []


class TestFetchScheduleRaw:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"name": "Test", "slug": "test"}}
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule_raw("testorg", "testslug")
            assert result["name"] == "Test"


class TestFetchSchedule:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "name": "Test Schedule",
                "slug": "test",
                "timezone": "Europe/Stockholm",
                "start": "2026-08-01T14:00:00+02:00",
                "columns": ["Game", "Players", "Platform", "Category", "Note", "Layout", "ID"],
                "setup_t": 600,
                "items": [
                    {
                        "data": ["Game1", "[Runner1](https://twitch.tv/r1)", "PC", "Any%", "", "", "123:cat1"],
                        "length": "PT30M",
                        "length_t": 1800,
                        "scheduled": "2026-08-01T14:00:00+02:00",
                    }
                ],
            }
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule("testorg", "testslug")
            assert result.name == "Test Schedule"
            assert len(result.items) == 1
            assert result.items[0].game == "Game1"
            assert result.items[0].submission_id == "123"
            assert result.items[0].category_id == "cat1"
            assert result.items[0].estimate_seconds == 1800
            assert result.items[0].setup_seconds == 600

    def test_with_setup_in_options(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "name": "Test",
                "slug": "test",
                "timezone": "Europe/Stockholm",
                "start": "2026-08-01T14:00:00+02:00",
                "columns": ["Game", "Players"],
                "setup_t": 0,
                "items": [
                    {
                        "data": ["Game1", "Runner1"],
                        "length": "PT30M",
                        "length_t": 1800,
                        "scheduled": "2026-08-01T14:00:00+02:00",
                        "options": {"setup": "10m"},
                    }
                ],
            }
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule("testorg", "testslug")
            assert result.items[0].setup_seconds == 600

    def test_manual_id(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "name": "Test",
                "slug": "test",
                "timezone": "Europe/Stockholm",
                "start": "2026-08-01T14:00:00+02:00",
                "columns": ["Game", "Players", "ID"],
                "setup_t": 0,
                "items": [
                    {
                        "data": ["Game1", "Runner1", "manual:123"],
                        "length": "PT30M",
                        "length_t": 1800,
                        "scheduled": "2026-08-01T14:00:00+02:00",
                    }
                ],
            }
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule("testorg", "testslug")
            assert result.items[0].submission_id is None
            assert result.items[0].category_id is None

    def test_runner_fallback_column(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "name": "Test",
                "slug": "test",
                "timezone": "Europe/Stockholm",
                "start": "2026-08-01T14:00:00+02:00",
                "columns": ["Game", "Runner", "Platform", "Category"],
                "setup_t": 0,
                "items": [
                    {
                        "data": ["Game1", "Runner1", "PC", "Any%"],
                        "length": "PT30M",
                        "length_t": 1800,
                        "scheduled": "2026-08-01T14:00:00+02:00",
                    }
                ],
            }
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule("testorg", "testslug")
            assert result.items[0].players == "Runner1"

    def test_empty_id_column(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "name": "Test",
                "slug": "test",
                "timezone": "Europe/Stockholm",
                "start": "2026-08-01T14:00:00+02:00",
                "columns": ["Game", "Players", "ID"],
                "setup_t": 0,
                "items": [
                    {
                        "data": ["Game1", "Runner1", ""],
                        "length": "PT30M",
                        "length_t": 1800,
                        "scheduled": "2026-08-01T14:00:00+02:00",
                    }
                ],
            }
        }
        with patch("src.horaro.requests.get", return_value=mock_resp):
            result = fetch_schedule("testorg", "testslug")
            assert result.items[0].submission_id is None
            assert result.items[0].category_id is None

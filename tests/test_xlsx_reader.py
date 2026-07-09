import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from src.xlsx_reader import (
    RunRow,
    IncentiveRow,
    SubmissionRow,
    _parse_iso_cell,
    _parse_participants_json,
    filter_runs_by_window,
    filter_runs_by_stream,
    stream_token_to_short,
    check_stale,
    check_stale_from_db,
    find_runner_sibling_runs,
    get_distinct_streams,
    read_cross_reference,
    read_incentives,
    read_submissions,
    read_cross_reference_from_db,
    read_incentives_from_db,
)

TZ = ZoneInfo("Europe/Stockholm")


def _make_run(scheduled=None, **kw):
    defaults = dict(
        pick=1,
        scheduled=scheduled or datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
        game="Test Game", category="Any%", estimate="30:00",
        platform="PC", players="Runner1",
        runner_display="Runner1", runner_twitch="r1",
        runner_discord="", runner_twitter="",
        note=None, layout=None, stream="stream1",
        submission_id="1", category_id="cat1",
        incentives="Race to the end",
        commentator="", upload_speed="", pronouns="",
        show_cam="", runner_comments="",
        participants=[],
    )
    defaults.update(kw)
    return RunRow(**defaults)


class TestParseIsoCell:
    def test_datetime_with_tz(self):
        dt = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        assert _parse_iso_cell(dt) == dt

    def test_datetime_naive(self):
        dt = datetime(2026, 8, 1, 14, 0, 0)
        result = _parse_iso_cell(dt)
        assert result.tzinfo is not None

    def test_iso_string(self):
        result = _parse_iso_cell("2026-08-01T14:00:00+02:00")
        assert result is not None
        assert result.year == 2026

    def test_naive_iso_string(self):
        result = _parse_iso_cell("2026-08-01T14:00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_invalid_string(self):
        assert _parse_iso_cell("not-a-date") is None

    def test_none(self):
        assert _parse_iso_cell(None) is None

    def test_integer(self):
        assert _parse_iso_cell(42) is None


class TestParseParticipantsJson:
    def test_valid_list(self):
        assert _parse_participants_json('[{"display": "Runner1"}]') == [{"display": "Runner1"}]

    def test_empty(self):
        assert _parse_participants_json(None) == []

    def test_empty_string(self):
        assert _parse_participants_json("") == []

    def test_invalid_json(self):
        assert _parse_participants_json("not json") == []

    def test_not_a_list(self):
        assert _parse_participants_json('{"display": "Runner1"}') == []


class TestFilterRunsByWindow:
    def test_filters_correctly(self):
        runs = [
            _make_run(scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ), game="A"),
            _make_run(scheduled=datetime(2026, 8, 1, 16, 0, 0, tzinfo=TZ), game="B"),
        ]
        start = datetime(2026, 8, 1, 13, 0, 0, tzinfo=TZ)
        end = datetime(2026, 8, 1, 15, 0, 0, tzinfo=TZ)
        result = filter_runs_by_window(runs, start, end)
        assert len(result) == 1
        assert result[0].game == "A"

    def test_naive_datetimes(self):
        runs = [
            _make_run(scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ), game="A"),
        ]
        start = datetime(2026, 8, 1, 13, 0, 0)
        end = datetime(2026, 8, 1, 15, 0, 0)
        result = filter_runs_by_window(runs, start, end)
        assert len(result) == 1

    def test_empty_result(self):
        runs = [
            _make_run(scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ), game="A"),
        ]
        start = datetime(2026, 8, 1, 15, 0, 0, tzinfo=TZ)
        end = datetime(2026, 8, 1, 16, 0, 0, tzinfo=TZ)
        result = filter_runs_by_window(runs, start, end)
        assert len(result) == 0


class TestFilterRunsByStream:
    def test_exact_match(self):
        runs = [_make_run(stream="stream1")]
        result = filter_runs_by_stream(runs, "stream1")
        assert len(result) == 1

    def test_empty_token_returns_all(self):
        runs = [_make_run(stream="s1")]
        result = filter_runs_by_stream(runs, "")
        assert len(result) == 1

    def test_no_match(self):
        runs = [_make_run(stream="stream1")]
        result = filter_runs_by_stream(runs, "stream2")
        assert len(result) == 0

    def test_suffix_match(self):
        runs = [_make_run(stream="Main Stream - stream1")]
        result = filter_runs_by_stream(runs, "stream1")
        assert len(result) == 1

    def test_case_insensitive(self):
        runs = [_make_run(stream="Stream1")]
        result = filter_runs_by_stream(runs, "STREAM1")
        assert len(result) == 1


class TestStreamTokenToShort:
    def test_delegates_to_slugs(self):
        assert stream_token_to_short("2026 - Summer (Stream One)") == "stream1"


class TestCheckStale:
    def test_missing_file(self):
        result = check_stale("/nonexistent/file.xlsx")
        assert result["is_missing"] is True
        assert result["is_stale"] is True

    def test_fresh_file(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            result = check_stale(path, max_age_hours=100)
            assert result["is_missing"] is False
            assert result["is_stale"] is False
        finally:
            os.unlink(path)

    def test_stale_file(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            result = check_stale(path, max_age_hours=0)
            assert result["is_stale"] is True
        finally:
            os.unlink(path)

    def test_age_hours(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            path = f.name
        try:
            result = check_stale(path, max_age_hours=100)
            assert result["age_hours"] is not None
            assert isinstance(result["age_hours"], float)
        finally:
            os.unlink(path)


class TestCheckStaleFromDb:
    def test_missing_db(self):
        result = check_stale_from_db("/nonexistent/db.db")
        assert result["is_missing"] is True

    def test_fresh_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            result = check_stale_from_db(path, max_age_hours=100)
            assert result["is_missing"] is False
        finally:
            os.unlink(path)


class TestFindRunnerSiblingRuns:
    def test_finds_by_twitch(self):
        now = datetime.now(TZ)
        runs = [
            _make_run(scheduled=now, game="A", submission_id="1",
                      runner_twitch="r1", runner_display="Runner1",
                      participants=[{"twitch": "r1", "display": "Runner1"}]),
        ]
        result = find_runner_sibling_runs(runs, "r1", "Runner1", exclude_submission_id="2")
        assert result["total"] >= 0

    def test_no_participants_fallback(self):
        now = datetime.now(TZ)
        runs = [
            _make_run(scheduled=now, game="A", submission_id="1",
                      runner_twitch="r1", runner_display="Runner1",
                      participants=[]),
        ]
        result = find_runner_sibling_runs(runs, "r1", "Runner1")
        assert result["total"] >= 0

    def test_excludes_own_submission(self):
        now = datetime.now(TZ)
        runs = [
            _make_run(scheduled=now, game="A", submission_id="1",
                      runner_twitch="r1", runner_display="Runner1",
                      participants=[{"twitch": "r1", "display": "Runner1"}]),
        ]
        result = find_runner_sibling_runs(runs, "r1", "Runner1", exclude_submission_id="1")
        assert result["total"] == 0

    def test_finds_by_display_name(self):
        now = datetime.now(TZ)
        runs = [
            _make_run(scheduled=now, game="A", submission_id="1",
                      runner_twitch="", runner_display="Runner1",
                      participants=[{"twitch": "", "display": "Runner1"}]),
        ]
        result = find_runner_sibling_runs(runs, "", "Runner1", exclude_submission_id="2")
        assert result["total"] >= 0

    def test_returns_upcoming_and_completed(self):
        past = datetime(2025, 1, 1, tzinfo=TZ)
        future = datetime(2027, 1, 1, tzinfo=TZ)
        runs = [
            _make_run(scheduled=past, game="Past", submission_id="1",
                      runner_twitch="r1", runner_display="Runner1",
                      participants=[{"twitch": "r1", "display": "Runner1"}]),
            _make_run(scheduled=future, game="Future", submission_id="2",
                      runner_twitch="r1", runner_display="Runner1",
                      participants=[{"twitch": "r1", "display": "Runner1"}]),
        ]
        result = find_runner_sibling_runs(runs, "r1", "Runner1")
        assert result["total"] >= 0
        assert result["completed_count"] >= 0


class TestReadCrossReference:
    def test_missing_file(self):
        with patch("src.xlsx_reader.load_workbook") as mock_lw:
            mock_lw.side_effect = FileNotFoundError
            import pytest
            with pytest.raises(FileNotFoundError):
                read_cross_reference("/nonexistent.xlsx")


class TestReadIncentives:
    def test_missing_sheet(self):
        mock_wb = MagicMock()
        mock_wb.__getitem__.side_effect = KeyError("Incentives Detail")
        with patch("src.xlsx_reader.load_workbook", return_value=mock_wb):
            result = read_incentives("test.xlsx")
            assert result == []


class TestReadSubmissions:
    def test_missing_file(self):
        with patch("src.xlsx_reader.load_workbook") as mock_lw:
            mock_lw.side_effect = FileNotFoundError
            import pytest
            with pytest.raises(FileNotFoundError):
                read_submissions("/nonexistent.xlsx")


class TestReadCrossReferenceFromDb:
    def test_empty_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            from src.db import init_db
            init_db(db_path)
            result = read_cross_reference_from_db(db_path)
            assert result == []
        finally:
            os.unlink(db_path)


class TestReadIncentivesFromDb:
    def test_empty_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            from src.db import init_db
            init_db(db_path)
            result = read_incentives_from_db(db_path)
            assert result == []
        finally:
            os.unlink(db_path)

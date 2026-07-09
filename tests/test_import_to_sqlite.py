from datetime import datetime
from zoneinfo import ZoneInfo

from src.import_to_sqlite import make_run_key

TZ = ZoneInfo("Europe/Stockholm")


class TestMakeRunKey:
    def test_basic(self):
        dt = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        key = make_run_key("123", "Super Mario 64", "Any%", dt)
        assert "123" in key
        assert "Super Mario 64" in key

    def test_different_inputs_different_keys(self):
        dt = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        k1 = make_run_key("1", "Game A", "Any%", dt)
        k2 = make_run_key("2", "Game B", "Any%", dt)
        assert k1 != k2

    def test_no_submission_id(self):
        dt = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
        key = make_run_key("", "Game", "Any%", dt)
        assert key.startswith("no-sub|")

from datetime import datetime
from zoneinfo import ZoneInfo

from src.oengus import (
    OengusMarathon,
    OengusSubmission,
    OengusUser,
    MfaRequired,
    set_auth_token,
    find_participant_submissions,
)
from src.horaro import ScheduleItem

TZ = ZoneInfo("Europe/Stockholm")


class TestSetAuthToken:
    def test_sets_session(self):
        set_auth_token("test-token")
        from src.oengus import _session
        assert _session is not None
        assert _session.headers["Authorization"] == "Bearer test-token"


class TestMfaRequired:
    def test_is_exception(self):
        assert issubclass(MfaRequired, Exception)


class TestOengusMarathon:
    def test_fields(self):
        m = OengusMarathon(
            id="m1", name="Test Marathon",
            start_date=datetime(2026, 8, 1, tzinfo=TZ),
            end_date=datetime(2026, 8, 3, tzinfo=TZ),
            submissions_end_date=datetime(2026, 7, 1, tzinfo=TZ),
        )
        assert m.id == "m1"
        assert m.name == "Test Marathon"


class TestOengusSubmission:
    def test_fields(self):
        user = OengusUser(id=1, username="Runner1", display_name="Runner1",
                          twitch="r1", discord="", twitter="")
        s = OengusSubmission(id=1, user=user)
        assert s.id == 1
        assert s.user.username == "Runner1"


class TestFindParticipantSubmissions:
    def test_finds_by_twitch(self):
        item = ScheduleItem(
            game="Test Game",
            players="[Runner1](https://twitch.tv/r1)",
            platform="PC",
            category="Any%",
            note=None,
            layout=None,
            submission_id=None,
            category_id=None,
            estimate_seconds=1800,
            scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
            setup_seconds=0,
            stream="s1",
        )
        user = OengusUser(id=1, username="Runner1", display_name="Runner1",
                          twitch="r1", discord="", twitter="")
        subs = [OengusSubmission(id=1, user=user)]
        result = find_participant_submissions(item, subs)
        assert len(result) >= 1

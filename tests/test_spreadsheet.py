from datetime import datetime
from zoneinfo import ZoneInfo

from src.spreadsheet import (
    CrossReferenceRow,
    _union_incentives,
    _find_answer_by_keyword,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestCrossReferenceRow:
    def test_fields(self):
        row = CrossReferenceRow(
            scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
            game="Test Game",
            category="Any%",
            estimate="30:00",
            platform="PC",
            players="Runner1",
            runner_display="Runner1",
            runner_twitch="r1",
            runner_discord="",
            runner_twitter="",
            note=None,
            layout=None,
            stream="stream1",
            submission_id="123",
            category_id="cat1",
            incentives="Race to the end",
            commentator="",
            upload_speed="",
            pronouns="",
            show_cam="",
            runner_comments="",
            participants=[],
        )
        assert row.game == "Test Game"


class TestUnionIncentives:
    def test_single_submission(self):
        class FakeSub:
            incentives = "Race to the end"
            answers = [{"label": "Incentives?", "answer": "Race to the end"}]
        assert _union_incentives([FakeSub()]) == "Race to the end"

    def test_multiple_submissions(self):
        class FakeSub1:
            incentives = "First incentive"
            answers = [{"label": "Incentives?", "answer": "First incentive"}]
        class FakeSub2:
            incentives = "Second incentive"
            answers = [{"label": "Incentives?", "answer": "Second incentive"}]
        result = _union_incentives([FakeSub1(), FakeSub2()])
        assert "First incentive" in result
        assert "Second incentive" in result

    def test_empty(self):
        class FakeSub:
            incentives = ""
            answers = []
        assert _union_incentives([FakeSub()]) == ""


class TestFindAnswerByKeyword:
    def test_found(self):
        class FakeSub:
            answers = [{"label": "Incentives?", "answer": "Race to the end"}]
        result = _find_answer_by_keyword(FakeSub(), ["incentive"])
        assert result == "Race to the end"

    def test_not_found(self):
        class FakeSub:
            answers = [{"label": "Other", "answer": "Something"}]
        assert _find_answer_by_keyword(FakeSub(), ["incentive"]) == ""

    def test_no_answers(self):
        class FakeSub:
            answers = []
        assert _find_answer_by_keyword(FakeSub(), ["incentive"]) == ""

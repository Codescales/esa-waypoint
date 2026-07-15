from src.brief_builder import build_brief, seconds_to_hms


class TestBuildBrief:
    def test_imports(self):
        assert build_brief is not None


class TestSecondsToHms:
    def test_sub_hour_omits_hours(self):
        assert seconds_to_hms(2307) == "38:27"

    def test_over_hour_includes_hours(self):
        assert seconds_to_hms(5907) == "1:38:27"

    def test_exactly_one_hour(self):
        assert seconds_to_hms(3600) == "1:00:00"

    def test_float_input(self):
        assert seconds_to_hms(5907.0) == "1:38:27"

    def test_zero(self):
        assert seconds_to_hms(0) == "0:00"

    def test_none_returns_question_mark(self):
        assert seconds_to_hms(None) == "?"

    def test_non_numeric_returns_question_mark(self):
        assert seconds_to_hms("N/A") == "?"

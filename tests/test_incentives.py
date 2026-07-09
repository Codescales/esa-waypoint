from datetime import datetime
from zoneinfo import ZoneInfo

from src.incentives import (
    split_incentives,
    extract_estimate_minutes,
    validate_incentive_for_game,
    guess_status,
    _game_keywords,
    _extract_mentioned_games,
    _normalise,
    generate_uuid,
    build_incentive_rows,
    IncentiveRow,
)

TZ = ZoneInfo("Europe/Stockholm")


class TestSplitIncentives:
    def test_empty_text(self):
        assert split_incentives("") == []

    def test_nada(self):
        assert split_incentives("nada") == []

    def test_none(self):
        assert split_incentives("None") == []

    def test_single_item(self):
        assert split_incentives("Just one incentive") == ["Just one incentive"]

    def test_numbered_split(self):
        text = "1. First incentive\n2. Second incentive\n3. Third incentive"
        result = split_incentives(text)
        assert len(result) == 3
        assert result[0].startswith("1.")

    def test_bullet_split(self):
        text = "- First bullet\n- Second bullet"
        result = split_incentives(text)
        assert len(result) == 2

    def test_unicode_bullet(self):
        text = "• First\n• Second"
        result = split_incentives(text)
        assert len(result) == 2

    def test_no_split_needed(self):
        text = "Just a single line of text"
        result = split_incentives(text)
        assert len(result) == 1


class TestExtractEstimateMinutes:
    def test_hh_mm(self):
        assert extract_estimate_minutes("Adds 5:00") == 300

    def test_hh_mm_ss(self):
        assert extract_estimate_minutes("Takes 1:30:00") == 90

    def test_minutes_word(self):
        assert extract_estimate_minutes("Adds 10 minutes") == 10

    def test_min_abbrev(self):
        assert extract_estimate_minutes("About 5 min") == 5

    def test_plus_minutes(self):
        assert extract_estimate_minutes("+15 min") == 15

    def test_estimate_is(self):
        assert extract_estimate_minutes("Estimate is 20 min") == 20

    def test_no_match(self):
        assert extract_estimate_minutes("No time here") is None

    def test_approximate(self):
        assert extract_estimate_minutes("Roughly 8 min") == 8

    def test_tilde(self):
        assert extract_estimate_minutes("~12 min") == 12

    def test_adds_about(self):
        assert extract_estimate_minutes("Adds about 5 minutes") == 5

    def test_approximately(self):
        assert extract_estimate_minutes("Approximately 3 min") == 3

    def test_around(self):
        assert extract_estimate_minutes("Around 7 min") == 7

    def test_m_without_word_boundary(self):
        assert extract_estimate_minutes("5m") == 5

    def test_m_within_word(self):
        result = extract_estimate_minutes("5mario")
        assert result is None or result == 5


class TestGameKeywords:
    def test_basic(self):
        kw = _game_keywords("Super Mario 64")
        assert "super mario 64" in kw
        assert "mario" in kw

    def test_short_words_excluded(self):
        kw = _game_keywords("The Legend of Zelda")
        assert "the" not in kw
        assert "legend" in kw

    def test_special_chars_replaced(self):
        kw = _game_keywords("Donkey Kong: Tropical Freeze")
        assert "donkey" in kw


class TestExtractMentionedGames:
    def test_title_case_phrases(self):
        result = _extract_mentioned_games("Playing Super Mario 64")
        assert "Playing Super Mario 64" in result

    def test_stop_words_filtered(self):
        result = _extract_mentioned_games("The Game")
        assert "The Game" not in result

    def test_short_phrases_filtered(self):
        result = _extract_mentioned_games("Hi")
        assert result == []

    def test_all_caps_single_word(self):
        result = _extract_mentioned_games("PLAYING")
        assert result == []

    def test_lowercase_start(self):
        result = _extract_mentioned_games("playing game")
        assert result == []


class TestValidateIncentiveForGame:
    def test_valid_match(self):
        result = validate_incentive_for_game(
            "Super Mario 64", [], "Race to the end of Super Mario 64"
        )
        assert result == "Valid"

    def test_invalid_other_game(self):
        result = validate_incentive_for_game(
            "Super Mario 64", ["Zelda"], "Race to the end of Zelda"
        )
        assert result == "Needs Review"

    def test_needs_review(self):
        result = validate_incentive_for_game(
            "Super Mario 64", [], "Some random text"
        )
        assert result == "Needs Review"

    def test_both_mentioned_returns_valid(self):
        result = validate_incentive_for_game(
            "Super Mario 64", ["Zelda"], "Race in Super Mario 64 and also Zelda"
        )
        assert result == "Valid"


class TestGuessStatus:
    def test_removed_preserved(self):
        assert guess_status("", "", "", "Removed") == "Removed"

    def test_approved_preserved(self):
        assert guess_status("", "", "", "Approved") == "Approved"

    def test_no_category(self):
        assert guess_status("", "Yes", "10") == "To-Do"

    def test_needs_information(self):
        assert guess_status("Poll", "Needs Review", "10") == "Needs Information"

    def test_unknown_estimate(self):
        assert guess_status("Poll", "Yes", "Unknown") == "Needs Information"

    def test_in_review(self):
        assert guess_status("Poll", "Yes", "10") == "In Review"

    def test_to_do_fallback(self):
        assert guess_status("Poll", "No", "10") == "To-Do"


class TestNormalise:
    def test_lower_and_strip(self):
        assert _normalise("  Hello  World  ") == "hello world"

    def test_multiple_spaces(self):
        assert _normalise("a   b") == "a b"


class TestGenerateUuid:
    def test_returns_string(self):
        uid = generate_uuid()
        assert isinstance(uid, str)
        assert len(uid) == 36


class TestBuildIncentiveRows:
    def test_empty_xref(self):
        result = build_incentive_rows([])
        assert result == []

    def test_skips_no_incentives(self):
        from src.xlsx_reader import RunRow
        xref = [RunRow(
            pick=1, scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
            game="Test", category="Any%", estimate="30:00", platform="PC",
            players="Runner1", runner_display="Runner1", runner_twitch="r1",
            runner_discord="", runner_twitter="", note=None, layout=None,
            stream="s1", submission_id="1", category_id="cat1",
            incentives="nada", commentator="", upload_speed="",
            pronouns="", show_cam="", runner_comments="",
        )]
        result = build_incentive_rows(xref)
        assert result == []

    def test_builds_rows(self):
        from src.xlsx_reader import RunRow
        xref = [RunRow(
            pick=1, scheduled=datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ),
            game="Test", category="Any%", estimate="30:00", platform="PC",
            players="Runner1", runner_display="Runner1", runner_twitch="r1",
            runner_discord="", runner_twitter="", note=None, layout=None,
            stream="s1", submission_id="1", category_id="cat1",
            incentives="Race to the end", commentator="", upload_speed="",
            pronouns="", show_cam="", runner_comments="",
        )]
        result = build_incentive_rows(xref)
        assert len(result) == 1
        assert result[0].incentive_text == "Race to the end"
        assert result[0].game == "Test"

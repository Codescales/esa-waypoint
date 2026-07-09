from src.find_incentives import (
    _normalize_text,
    _game_keywords,
    _categorize_bid,
)


class TestNormalizeText:
    def test_lowercase(self):
        assert _normalize_text("Hello World") == "hello world"

    def test_accented_chars(self):
        result = _normalize_text("Pokémon")
        assert "é" not in result

    def test_html_entities(self):
        assert _normalize_text("Mario & Luigi") == "mario and luigi"

    def test_multiple_spaces(self):
        assert _normalize_text("hello   world") == "hello world"


class TestGameKeywords:
    def test_basic(self):
        kw = _game_keywords("Super Mario 64")
        assert kw["normalized"] == "super mario 64"
        assert "mario" in kw["meaningful"]

    def test_short_words_excluded(self):
        kw = _game_keywords("The Legend of Zelda")
        assert "the" not in kw["meaningful"]
        assert "legend" in kw["meaningful"]


class TestCategorizeBid:
    def test_reward(self):
        bid = {"name": "New PB", "description": "Race to the end", "is_choice": False}
        assert _categorize_bid(bid) == "Reward"

    def test_poll_bid_war(self):
        bid = {"name": "Pick a character", "description": "Choose who to play", "is_choice": True}
        assert _categorize_bid(bid) == "Poll-Bid War"

    def test_target(self):
        bid = {"name": "Bonus boss", "description": "If met, fight bonus boss"}
        assert _categorize_bid(bid) == "Target"

    def test_unknown(self):
        bid = {"name": "Some bid", "description": "Some description"}
        assert _categorize_bid(bid) == "Reward"

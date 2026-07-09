from src.evaluate import (
    _parse_estimate,
    _normalize,
    _tokenize,
    _semantic_match,
    _classify_incentive_text,
)


class TestParseEstimate:
    def test_hh_mm_ss(self):
        assert _parse_estimate("1:30:00") == 90

    def test_mm_ss(self):
        assert _parse_estimate("5:30") == 5

    def test_empty(self):
        assert _parse_estimate("") == 0


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Hello World") == "hello world"

    def test_accented(self):
        assert _normalize("Pokémon") == "pokemon"

    def test_special_chars(self):
        assert _normalize("Donkey Kong 64!") == "donkey kong 64"


class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Race to the end of the game")
        assert "race" in tokens
        assert "end" in tokens
        assert "the" not in tokens

    def test_empty(self):
        assert _tokenize("") == set()


class TestSemanticMatch:
    def test_exact_match(self):
        assert _semantic_match("Race to the end", "Race to the end") is True

    def test_partial_match(self):
        assert _semantic_match("Race to the end of the game", "Race to the end") is True

    def test_no_match(self):
        assert _semantic_match("Completely different", "Race to the end") is False


class TestClassifyIncentiveText:
    def test_poll_bid_war(self):
        assert _classify_incentive_text("Pick a character") == "Poll-Bid War"

    def test_target(self):
        assert _classify_incentive_text("If met, bonus boss") == "Target"

    def test_reward(self):
        assert _classify_incentive_text("Race to the end") == "Reward"

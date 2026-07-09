import json
from unittest.mock import patch, MagicMock
from io import BytesIO

from src.src_api import (
    src_get,
    search_src_game,
    fetch_src_categories,
    fetch_src_subcategories,
    fetch_category_wr,
    fetch_game_records,
    search_user_by_lookup,
    fetch_user_profile,
    fetch_user_personal_bests,
    SrcApiError,
)


def _mock_response(data, status=200):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = json.dumps(data).encode("utf-8")
    resp.status = status
    return resp


def _mock_http_error(code, reason="Error"):
    from urllib.error import HTTPError
    return HTTPError("/path", code, reason, {}, None)


class TestSrcGet:
    def test_success(self):
        with patch("urllib.request.urlopen") as mock:
            mock.return_value = _mock_response({"data": ["ok"]})
            result = src_get("/games?name=test")
            assert result == {"data": ["ok"]}

    def test_404_returns_none(self):
        with patch("urllib.request.urlopen") as mock:
            mock.side_effect = _mock_http_error(404)
            result = src_get("/games?name=missing")
            assert result is None

    def test_429_retries_then_succeeds(self):
        with patch("urllib.request.urlopen") as mock:
            mock.side_effect = [
                _mock_http_error(429),
                _mock_response({"data": ["ok"]}),
            ]
            with patch("src.src_api.time.sleep"):
                result = src_get("/games?name=test")
                assert result == {"data": ["ok"]}

    def test_5xx_raises(self):
        with patch("urllib.request.urlopen") as mock:
            mock.side_effect = _mock_http_error(500)
            import pytest
            with pytest.raises(SrcApiError):
                src_get("/games?name=5xx-test")

    def test_cache_hit(self):
        with patch("urllib.request.urlopen") as mock:
            mock.return_value = _mock_response({"data": ["cached"]})
            first = src_get("/games?name=cached")
            second = src_get("/games?name=cached")
            assert first == second
            assert mock.call_count == 1


class TestSearchSrcGame:
    def test_exact_match(self):
        data = {
            "data": [
                {"names": {"international": "Super Mario 64", "twitch": "sm64"}},
                {"names": {"international": "Mario 64", "twitch": "m64"}},
            ]
        }
        with patch("src.src_api.src_get", return_value=data):
            result = search_src_game("Super Mario 64")
            assert result["names"]["international"] == "Super Mario 64"

    def test_no_data_returns_none(self):
        with patch("src.src_api.src_get", return_value=None):
            assert search_src_game("Nonexistent Game") is None

    def test_empty_data_returns_none(self):
        with patch("src.src_api.src_get", return_value={"data": []}):
            assert search_src_game("Empty Game") is None


class TestFetchSrcCategories:
    def test_basic(self):
        data = {"data": [{"id": "c1", "name": "Any%"}]}
        with patch("src.src_api.src_get", return_value=data):
            result = fetch_src_categories("g1")
            assert len(result) == 1
            assert result[0]["name"] == "Any%"


class TestFetchSrcSubcategories:
    def test_returns_interesting_vars(self):
        data = {
            "data": [
                {
                    "is-subcategory": True,
                    "name": "Character",
                    "id": "v1",
                    "scope": {"type": "full-game"},
                    "values": {"values": {"v1": {"label": "Mario"}, "v2": {"label": "Luigi"}}},
                }
            ]
        }
        with patch("src.src_api.src_get", return_value=data):
            result = fetch_src_subcategories("g1")
            assert len(result) == 1
            assert result[0]["name"] == "Character"

    def test_no_data(self):
        with patch("src.src_api.src_get", return_value=None):
            assert fetch_src_subcategories("g1") == []


class TestFetchCategoryWr:
    def test_returns_time(self):
        data = {"data": [{"runs": [{"run": {"times": {"primary_t": 1234.5}}}]}]}
        with patch("src.src_api.src_get", return_value=data):
            result = fetch_category_wr("g1", "c1")
            assert result == 1234.5

    def test_no_data(self):
        with patch("src.src_api.src_get", return_value=None):
            assert fetch_category_wr("g1", "c1") is None


class TestFetchGameRecords:
    def test_basic(self):
        with patch("src.src_api.fetch_src_categories", return_value=[{"id": "c1", "name": "Any%"}]), \
             patch("src.src_api.src_get", return_value={
                 "data": [{
                     "category": "c1",
                     "runs": [{"run": {"times": {"primary_t": 100.0}, "players": [{"id": "p1"}]}}],
                 }]
             }):
            result = fetch_game_records("g1")
            assert len(result) == 1
            assert result[0]["category_name"] == "Any%"
            assert result[0]["wr_seconds"] == 100.0


class TestSearchUserByLookup:
    def test_found(self):
        with patch("src.src_api.src_get", return_value={"data": [{"id": "u1", "names": {"international": "Runner"}}]}):
            result = search_user_by_lookup("Runner")
            assert result["id"] == "u1"

    def test_empty_handle(self):
        assert search_user_by_lookup("") is None

    def test_not_found(self):
        with patch("src.src_api.src_get", return_value=None):
            assert search_user_by_lookup("Nobody") is None


class TestFetchUserProfile:
    def test_found(self):
        with patch("src.src_api.src_get", return_value={"data": {"id": "u1", "location": {"country": {"name": "SE"}}}}):
            result = fetch_user_profile("u1")
            assert result["id"] == "u1"

    def test_not_found(self):
        with patch("src.src_api.src_get", return_value=None):
            assert fetch_user_profile("u1") is None


class TestFetchUserPersonalBests:
    def test_basic(self):
        data = {
            "data": [
                {
                    "run": {"category": "c1", "times": {"primary_t": 100.0}},
                    "game": {"data": {"names": {"international": "Game1"}, "abbreviation": "g1", "id": "g1"}},
                    "category": {"data": {"name": "Any%"}},
                }
            ],
            "pagination": {"size": 1},
        }
        with patch("src.src_api.src_get", return_value=data):
            result = fetch_user_personal_bests("u1")
            assert len(result) == 1
            assert result[0]["game_name"] == "Game1"

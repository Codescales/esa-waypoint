"""Speedrun.com API client — canonical shared helper.

Functions for game/category/record/user lookups. In-memory result cache
avoids redundant API calls within a single process invocation.

Migrate find_incentives.py to import from here (follow-up task).
"""

import json
import time
import urllib.parse
import urllib.request

SRC_API = "https://www.speedrun.com/api/v1"
SRC_HEADERS = {"User-Agent": "esa-brief-skill/0.1 (ESA Summer 2026; host briefing tool)"}

_cache: dict[str, dict | list | None] = {}


class SrcApiError(Exception):
    """Raised on non-recoverable SRC API errors (5xx, rate-limit exhausted)."""


def _cache_key(path: str) -> str:
    return path


def src_get(path: str, _retry: bool = True) -> dict | None:
    """GET an SRC API endpoint. Returns parsed JSON or None on 404.

    Retries once on 429 (rate limit) with 5s backoff.
    Raises SrcApiError on 5xx or if retries exhausted.
    """
    key = _cache_key(path)
    if key in _cache:
        return _cache[key]

    url = f"{SRC_API}{path}"
    try:
        req = urllib.request.Request(url, headers=SRC_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: dict = json.loads(resp.read().decode("utf-8"))
            _cache[key] = data
            return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _cache[key] = None
            return None
        if e.code == 429 and _retry:
            time.sleep(5)
            return src_get(path, _retry=False)
        raise SrcApiError(f"SRC API error {e.code} for {path}: {e.reason}") from e
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise SrcApiError(f"SRC API request failed for {path}: {e}") from e


def search_src_game(game_name: str) -> dict | None:
    """Search speedrun.com for a game. Returns the best match or None.

    Prefers exact international-name match, then first result.
    """
    resp = src_get(f"/games?name={urllib.parse.quote(game_name)}&max=10")
    if not resp or not resp.get("data"):
        return None
    name_lower = game_name.lower()
    for g in resp["data"]:
        names = g.get("names", {})
        if names.get("international", "").lower() == name_lower:
            return g
        if names.get("twitch", "").lower() == name_lower:
            return g
    return resp["data"][0]


def fetch_src_categories(game_id: str) -> list[dict]:
    """Fetch all categories for a game (handles pagination)."""
    key = f"/games/{game_id}/categories"
    if key in _cache:
        return _cache[key]  # type: ignore[return-value]
    categories: list[dict] = []
    offset = 0
    while True:
        resp = src_get(f"/games/{game_id}/categories?offset={offset}&max=200")
        if not resp or not resp.get("data"):
            break
        categories.extend(resp["data"])
        if not resp.get("pagination", {}).get("offset", 0) + len(resp["data"]) < resp.get("pagination", {}).get("size", 0):
            break
        if len(resp["data"]) < 200:
            break
        offset += 200
    _cache[key] = categories
    return categories


def fetch_src_subcategories(game_id: str) -> list[dict]:
    """Fetch subcategory variables from speedrun.com.

    Returns variables that represent player choices (character, difficulty, route)
    — useful for Poll-Bid War incentive suggestions. Excludes platform/version/
    language variables. Included here for future find_incentives.py migration.
    """
    resp = src_get(f"/games/{game_id}/variables")
    if not resp or not resp.get("data"):
        return []

    choice_keywords = {"character", "difficulty", "route", "campaign", "story",
                       "ending", "path", "mode", "type", "run type",
                       "weapon", "power", "style", "class", "build", "scheduled"}

    interesting: list[dict] = []
    for v in resp["data"]:
        if not v.get("is-subcategory"):
            continue
        name_lower = v["name"].lower()
        if not any(kw in name_lower for kw in choice_keywords):
            continue

        if v["scope"]["type"] not in ("full-game", "global"):
            continue

        vals = v["values"].get("values", v["values"].get("choices", {}))
        options = [v2.get("label", k) for k, v2 in vals.items()]
        if len(options) < 2:
            continue

        interesting.append({
            "name": v["name"],
            "options": options,
            "id": v["id"],
        })

    return interesting


def fetch_category_wr(game_id: str, category_id: str) -> float | None:
    """Fetch the world record time (in seconds) for a category.

    Returns the primary time of the top run, or None if no records exist.
    Kept for compatibility with find_incentives.py migration.
    """
    resp = src_get(f"/categories/{category_id}/records?top=1&embed=players")
    if not resp or not resp.get("data"):
        return None
    runs = resp["data"][0].get("runs", [])
    if not runs:
        return None
    return runs[0]["run"]["times"].get("primary_t")


def fetch_game_records(game_id: str) -> list[dict]:
    """Fetch world record for every category of a game in one call.

    Returns:
        list of {category_id, category_name, wr_seconds, runner_name, runner_id}
    """
    key = f"/games/{game_id}/records"
    if key in _cache:
        return _cache[key]  # type: ignore[return-value]

    categories = fetch_src_categories(game_id)
    cat_map = {c["id"]: c["name"] for c in categories}

    resp = src_get(f"/games/{game_id}/records?top=1&max=200&embed=players")
    records: list[dict] = []
    if not resp or not resp.get("data"):
        return records

    for entry in resp["data"]:
        cat_id = entry.get("category")
        cat_name = cat_map.get(cat_id, "unknown")
        runs = entry.get("runs", [])
        if not runs:
            continue
        run = runs[0]["run"]
        wr_sec = run.get("times", {}).get("primary_t")
        players = run.get("players", [])
        runner = players[0].get("id", "") if players else ""
        records.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "wr_seconds": wr_sec,
            "runner_id": runner,
        })

    _cache[key] = records
    return records


def search_user_by_lookup(handle: str) -> dict | None:
    """Search speedrun.com for a user by name or Twitch handle.

    Uses the ?lookup= query parameter which matches display names and
    Twitch usernames. Returns the user object or None. Returns None
    (not an exception) for empty input — the API returns 400 for
    `?lookup=` with no value.
    """
    handle = (handle or "").strip()
    if not handle:
        return None
    resp = src_get(f"/users?lookup={urllib.parse.quote(handle)}")
    if not resp or not resp.get("data"):
        return None
    return resp["data"][0]


def fetch_user_profile(user_id: str) -> dict | None:
    """Fetch a single SRC user by id. Returns the user object or None.

    Used to pull fields the /users?lookup= response may omit (signup,
    aboutme, location). Falls back to None on 404.
    """
    resp = src_get(f"/users/{user_id}")
    if not resp or not resp.get("data"):
        return None
    return resp["data"]


def fetch_user_personal_bests(user_id: str, max_count: int = 200) -> list[dict]:
    """Fetch a user's personal bests across all games.

    Returns list of {game_name, game_abbr, game_id, category_id,
    category_name, time_seconds}. Embedded game data included.
    Handles pagination for users with >200 PBs.
    """
    key = f"/users/{user_id}/personal-bests"
    if key in _cache:
        return _cache[key]  # type: ignore[return-value]

    pbs: list[dict] = []
    offset = 0
    while True:
        resp = src_get(f"/users/{user_id}/personal-bests?embed=game,category&max={max_count}&offset={offset}")
        if not resp or not resp.get("data"):
            break
        for entry in resp["data"]:
            run = entry.get("run", {})
            # Embedded game data is at entry[game][data], not inside run
            game_data = None
            embed_game = entry.get("game")
            if isinstance(embed_game, dict) and isinstance(embed_game.get("data"), dict):
                game_data = embed_game["data"]
            if not game_data:
                continue
            cat_id = run.get("category", "")
            cat_name = ""
            embed_category = entry.get("category")
            if isinstance(embed_category, dict) and isinstance(embed_category.get("data"), dict):
                cat_name = (embed_category["data"].get("name", ""))
            pbs.append({
                "game_name": (game_data.get("names", {}) or {}).get("international", ""),
                "game_abbr": game_data.get("abbreviation", ""),
                "game_id": game_data.get("id", ""),
                "category_id": cat_id,
                "category_name": cat_name,
                "time_seconds": (run.get("times", {}) or {}).get("primary_t"),
            })
        pagination = resp.get("pagination", {}) or {}
        size = pagination.get("size", 0)
        if offset + len(resp["data"]) >= size:
            break
        offset += max_count

    _cache[key] = pbs
    return pbs

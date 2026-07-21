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
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
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

    user_cache: dict[str, str] = {}

    def _resolve_runner_name(uid: str) -> str:
        if uid in user_cache:
            return user_cache[uid]
        try:
            user = src_get(f"/users/{uid}")
            if user and user.get("data"):
                name = (user.get("data", {}).get("names", {}) or {}).get("international", "")
                user_cache[uid] = name
                return name
        except Exception:
            pass
        user_cache[uid] = ""
        return ""

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
        runner_name = _resolve_runner_name(runner) if runner else ""
        records.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "wr_seconds": wr_sec,
            "runner_id": runner,
            "runner_name": runner_name,
            "date": run.get("date", ""),
        })

    _cache[key] = records
    return records


def fetch_category_leaderboard(game_id: str, category_id: str, top: int = 200) -> list[dict]:
    """Fetch the full leaderboard for a single category.

    Returns list of {runner_id, runner_name, time_seconds, date} for every run
    on the leaderboard, up to `top` entries. Used to count unique runners in
    a category (the /records?top=1 endpoint only returns the WR).

    Falls back to the embedded players resolution like fetch_game_records.
    """
    key = f"/leaderboards/{game_id}/{category_id}?top={top}"
    if key in _cache:
        return _cache[key]  # type: ignore[return-value]

    resp = src_get(f"/leaderboards/{game_id}/category/{category_id}?top={top}&embed=players")
    if not resp or not resp.get("data"):
        _cache[key] = []
        return []

    runs_data = resp["data"].get("runs", [])
    if not runs_data:
        _cache[key] = []
        return []

    user_cache: dict[str, str] = {}

    def _resolve_runner_name(uid: str) -> str:
        if uid in user_cache:
            return user_cache[uid]
        try:
            user = src_get(f"/users/{uid}")
            if user and user.get("data"):
                name = (user.get("data", {}).get("names", {}) or {}).get("international", "")
                user_cache[uid] = name
                return name
        except Exception:
            pass
        user_cache[uid] = ""
        return ""

    entries: list[dict] = []
    for entry in runs_data:
        run = entry.get("run", {})
        players = run.get("players", [])
        runner_id = players[0].get("id", "") if players else ""
        runner_name = _resolve_runner_name(runner_id) if runner_id else ""
        entries.append({
            "runner_id": runner_id,
            "runner_name": runner_name,
            "time_seconds": run.get("times", {}).get("primary_t"),
            "date": run.get("date", ""),
            "place": entry.get("place"),
        })

    _cache[key] = entries
    return entries


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


# ── Wikipedia trivia helpers ─────────────────────────────────────────────────
# Lightweight fetchers used by brief_builder.py to produce trivia candidates
# that the LLM validates before including in the "Trivia & Interesting Facts"
# section of the brief. The LLM is responsible for filtering; this code only
# provides raw material.

WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKI_HEADERS = {"User-Agent": "esa-brief-skill/0.1 (ESA Summer 2026; host briefing tool)"}

_wiki_cache: dict[str, str | None] = {}


def _wiki_slug(game_name: str) -> str:
    """Convert a game name to a likely Wikipedia slug.

    Strips common suffixes like "(Recompiled)", ":", replaces spaces with
    underscores. The LLM (and downstream call) can re-search if the slug
    doesn't resolve.
    """
    s = game_name.strip()
    # Strip parentheticals like "(Recompiled)", "(HD)"
    import re as _re
    s = _re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    s = s.replace(" ", "_")
    return s


def fetch_wikipedia_summary(game_name: str) -> str | None:
    """Fetch the Wikipedia summary extract for a game.

    Returns the plain-text extract (up to ~500 chars) or None if not found.
    Cached per-process. Used by gather_trivia_candidates() to produce raw
    material the LLM validates.
    """
    slug = _wiki_slug(game_name)
    if slug in _wiki_cache:
        return _wiki_cache[slug]
    try:
        req = urllib.request.Request(f"{WIKI_API}/{slug}", headers=WIKI_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
        extract = data.get("extract") or ""
        if not extract:
            _wiki_cache[slug] = None
            return None
        # Trim to keep prompts small.
        if len(extract) > 600:
            extract = extract[:597] + "..."
        _wiki_cache[slug] = extract
        return extract
    except Exception:
        _wiki_cache[slug] = None
        return None


def gather_trivia_candidates(game_name: str, max_results: int = 3) -> list[str]:
    """Return a list of trivia candidate strings for the given game.

    Currently a single Wikipedia summary extract. Returns [] if no summary
    is found. The LLM is responsible for validating before including in
    the brief.
    """
    summary = fetch_wikipedia_summary(game_name)
    if not summary:
        return []
    return [summary]

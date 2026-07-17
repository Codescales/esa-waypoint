"""Speedrun.com news fetcher for the news ticker.

Given a list of game names (e.g. games in the current ESA schedule), resolve
their speedrun.com game IDs and fetch recently-verified runs. Runs placing
first are surfaced as world records ("wr"); others as new verified runs
("new_run").

speedrun.com has no global "recent WRs" endpoint, so we poll per game via
`/runs?game={id}&status=verified&orderby=verify-date&direction=desc`. Reuses
the shared client in src_api (in-process cache + 429 retry).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from . import src_api


SOURCE = "speedrun"
SOURCE_LABEL = "speedrun.com"


def _fmt_time(seconds: float | None) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _players_names(run: dict) -> str:
    """Extract runner display names from an embedded players block."""
    players = run.get("players", {})
    data = players.get("data", []) if isinstance(players, dict) else players
    names: list[str] = []
    for p in data or []:
        if not isinstance(p, dict):
            continue
        # registered users have names.international; guests have a name field
        n = (p.get("names", {}) or {}).get("international") or p.get("name") or ""
        if n:
            names.append(n)
    return ", ".join(names)


def _parse_verify_date(run: dict) -> datetime | None:
    status = run.get("status", {}) or {}
    raw = status.get("verify-date") or run.get("date")
    if not raw:
        return None
    try:
        # verify-date is ISO 8601 with Z; date is YYYY-MM-DD
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_for_game(game_name: str, top_n: int = 3) -> list[dict]:
    """Fetch recent verified runs for a single game by name.

    Returns a list of news-item dicts (source/category/title/url/summary/
    published_at/dedupe_key). Empty if the game can't be resolved.
    """
    game = src_api.search_src_game(game_name)
    if not game:
        return []
    game_id = game.get("id")
    game_display = (game.get("names", {}) or {}).get("international") or game_name
    if not game_id:
        return []

    resp = src_api.src_get(
        f"/runs?game={game_id}&status=verified&orderby=verify-date"
        f"&direction=desc&embed=players,category&max={top_n}"
    )
    if not resp or not resp.get("data"):
        return []

    items: list[dict] = []
    for run in resp["data"]:
        run_id = run.get("id")
        if not run_id:
            continue
        cat = run.get("category", {})
        cat_name = ""
        if isinstance(cat, dict) and isinstance(cat.get("data"), dict):
            cat_name = cat["data"].get("name", "")
        place = run.get("place")  # present on leaderboard embeds; may be absent
        is_wr = place == 1
        primary_t = (run.get("times", {}) or {}).get("primary_t")
        time_str = _fmt_time(primary_t)
        runners = _players_names(run)
        weblink = run.get("weblink", "")

        label = "New WR" if is_wr else "New run"
        parts = [f"{game_display}"]
        if cat_name:
            parts.append(cat_name)
        title = f"{label}: {' '.join(parts)}"
        if time_str:
            title += f" \u2014 {time_str}"
        if runners:
            title += f" by {runners}"

        items.append({
            "source": SOURCE,
            "source_label": SOURCE_LABEL,
            "category": "wr" if is_wr else "new_run",
            "title": title,
            "url": weblink,
            "summary": "",
            "published_at": _parse_verify_date(run),
            "dedupe_key": f"{SOURCE}:{run_id}",
        })
    return items


def fetch_news(game_names: Iterable[str], top_n: int = 3) -> list[dict]:
    """Fetch speedrun news across the given games.

    De-duplicates game names, skips games that fail to resolve, and collects
    all items. Network/parse errors for a single game are swallowed so one bad
    game doesn't abort the whole refresh.
    """
    seen: set[str] = set()
    items: list[dict] = []
    for name in game_names:
        key = (name or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            items.extend(fetch_for_game(name, top_n=top_n))
        except src_api.SrcApiError:
            continue
        except Exception:
            continue
    return items

"""Horaro schedule data fetcher.

Uses the stable Horaro API v1:
  https://horaro.net/-/api/v1/events/{org}/schedules/{slug}
  https://horaro.net/-/api/v1/schedules/{id}

The public JSON exports (.json?named=true) are not recommended for automation.
"""

import re
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScheduleItem:
    game: str
    players: str
    platform: str
    category: str
    note: Optional[str]
    layout: Optional[str]
    submission_id: Optional[str]
    category_id: Optional[str]
    estimate_seconds: int
    scheduled: datetime
    setup_seconds: int
    stream: str

    @property
    def estimate_str(self) -> str:
        h = self.estimate_seconds // 3600
        m = (self.estimate_seconds % 3600) // 60
        s = self.estimate_seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @property
    def runner_names(self) -> list[str]:
        """Extract plain runner names from the players markdown string."""
        names = re.findall(r"\[([^\]]+)\]\([^)]+\)", self.players)
        return names if names else [self.players]

    @property
    def runner_twitch(self) -> list[str]:
        """Extract Twitch usernames from player links."""
        urls = re.findall(r"https://twitch\.tv/([^\s)]+)", self.players)
        return urls

    @property
    def participants(self) -> list[dict]:
        """Extract ordered participant entries from the players markdown string.

        Each entry: `{"display": <link text>, "twitch": <handle or "">, "raw_url": <url or "">}`.

        Format notes:
        - Primary: `[name](https://twitch.tv/handle)` — link text + twitch handle.
        - Legacy: `[name](https://oengus.io/user/xxx)` — link text only, twitch empty.
        - Plain text: comma-separated names — no markdown links at all; each
          comma-separated part becomes a participant with empty twitch.
        """
        entries: list[dict] = []
        for m in re.finditer(r"\[([^\]]+)\]\((https?://[^\)]+)\)", self.players or ""):
            text = m.group(1).strip()
            url = m.group(2).strip()
            twitch_match = re.search(r"https?://twitch\.tv/([^\s/)]+)", url)
            twitch = (twitch_match.group(1) if twitch_match else "").lower()
            entries.append({"display": text, "twitch": twitch, "raw_url": url})

        if entries:
            return entries

        if self.players:
            names = [n.strip() for n in self.players.split(",") if n.strip()]
            return [{"display": n, "twitch": "", "raw_url": ""} for n in names]

        return []

    @property
    def is_multi_player(self) -> bool:
        """True if the players cell encodes more than one runner."""
        return len(self.participants) > 1

    def mentions_runner(self, name: str, twitch: str = "") -> bool:
        """True if this item's `players` markdown features `name` (or `twitch`).

        Old ESA schedules only embed the display name in a markdown link
        (e.g. `[Jazz](https://oengus.io/user/Jazz)`). Current schedules
        include a Twitch URL. Even older schedules put the name in
        plain text (e.g. `Cropax , MrWalrus3451`). We match
        case-insensitively against:
          - the bare display names from `runner_names` (exact match)
          - the name as a word-boundary substring of the players cell
            (catches plain-text comma-separated names with trailing
            spaces — uses \\b so "An" doesn't match "Nathan")
          - the Twitch username in `players` (no word boundary,
            since handles can be embedded in URLs)
        """
        if not name and not twitch:
            return False
        name_lower = (name or "").strip().lower()
        twitch_lower = (twitch or "").strip().lower()
        for n in self.runner_names:
            if name_lower and n.strip().lower() == name_lower:
                return True
        players_lower = (self.players or "").lower()
        if name_lower and re.search(rf"\b{re.escape(name_lower)}\b", players_lower):
            return True
        if twitch_lower and twitch_lower in players_lower:
            return True
        return False


@dataclass
class Schedule:
    name: str
    slug: str
    timezone_str: str
    start: datetime
    items: list[ScheduleItem] = field(default_factory=list)


def parse_iso_duration(duration: str) -> int:
    """Parse ISO 8601 duration (PT1H30M, PT35M, PT12S) to total seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    h, m, s = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + int(s or 0)


def parse_horaro_datetime(dt_str: str) -> datetime:
    """Parse a Horaro datetime string like '2026-08-01T14:00:00+02:00'."""
    return datetime.fromisoformat(dt_str)


def list_event_schedules(org: str) -> list[dict]:
    """List every schedule under a Horaro event (org).

    Returns a list of `{slug, name, start, id}` dicts, oldest first.
    Used by the brief skill to walk all past ESA events and find runner
    appearances without hard-coding a slug list.
    """
    url = f"https://horaro.net/-/api/v1/events/{org}/schedules"
    resp = requests.get(url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    out: list[dict] = []
    for s in data:
        out.append({
            "slug": s.get("slug", ""),
            "name": s.get("name", ""),
            "start": s.get("start", ""),
            "id": s.get("id", ""),
        })
    out.sort(key=lambda x: x.get("start", ""))
    return out


def _norm_col(name: str) -> str:
    """Normalize a column header to the key used in col_map.

    Lower-cases, strips spaces/parens, and folds common variants
    (e.g. "Players / Runners" -> "players_runners").
    """
    return (
        (name or "")
        .lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "_")
    )


def fetch_schedule_raw(org: str, slug: str) -> dict:
    """Fetch a Horaro schedule and return its raw JSON.

    Returns the `data` dict from the API response (columns, items,
    name, slug, start, etc.) untouched. Used by the brief skill to
    inspect old ESA schedules whose column layouts differ from the
    current 6-column layout assumed by `fetch_schedule`.
    """
    url = f"https://horaro.net/-/api/v1/events/{org}/schedules/{slug}"
    resp = requests.get(url, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    return resp.json()["data"]


def match_runner_in_items(items: list[dict], col_map: dict[str, int], name: str, twitch: str = "") -> list[dict]:
    """Return schedule items whose player column mentions `name` or `twitch`.

    `col_map` is a `normalized_column_name -> index` map (see `_norm_col`).
    The player column is the first present of: `players`, `runner`, or
    `players_runners`. The game/category/estimate columns follow the
    same fallback logic so 3-, 4-, 5-, and 6-column ESA schedules are
    all queryable.
    """
    if not name and not twitch:
        return []
    name_lower = (name or "").strip().lower()
    twitch_lower = (twitch or "").strip().lower()
    player_idx = next(
        (col_map[k] for k in ("players", "runner", "players_runners") if k in col_map),
        None,
    )
    if player_idx is None:
        return []
    matched: list[dict] = []
    for item in items:
        row = item.get("data") or []
        if player_idx >= len(row):
            continue
        players_cell = str(row[player_idx] or "")
        players_lower = players_cell.lower()
        hit_twitch = bool(twitch_lower and twitch_lower in players_lower)
        hit_name = False
        if name_lower:
            for raw in re.findall(r"\[([^\]]+)\]\([^)]+\)", players_cell):
                if raw.strip().lower() == name_lower:
                    hit_name = True
                    break
            if not hit_name and name_lower in players_lower:
                hit_name = True
        if not (hit_twitch or hit_name):
            continue
        matched.append({
            "item": item,
            "match": "twitch" if hit_twitch else "name",
        })
    return matched


def fetch_schedule(org: str, slug: str) -> Schedule:
    """Fetch a Horaro schedule via the stable API v1.

    Uses GET /-/api/v1/events/{org}/schedules/{slug} which redirects
    to the canonical /-/api/v1/schedules/{id} endpoint.
    """
    url = f"https://horaro.net/-/api/v1/events/{org}/schedules/{slug}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    sched = resp.json()["data"]

    columns = sched["columns"]
    default_setup_s = sched.get("setup_t", 0)

    col_map = {_norm_col(name): idx for idx, name in enumerate(columns)}

    def _cell(name: str, fallback: int) -> str:
        """Return the cell value for column `name`, or '' if missing.

        Falls back to `fallback` only when the column is present but
        empty. Crucially, returns '' (instead of pulling the wrong
        column) when the column is absent — this protects against
        old ESA schedules with fewer than 6 columns.
        """
        idx = col_map.get(name)
        if idx is None or idx >= len(d):
            return ""
        val = d[idx]
        return val if val is not None else ""

    items = []
    for item in sched["items"]:
        d = item["data"]
        game = _cell("game", 0)
        players = _cell("players", 1)
        # Older ESA schedules label the player column "runner"; fall
        # back to that so legacy items still get a player string.
        if not players and "runner" in col_map:
            players = _cell("runner", 1)
        platform = _cell("platform", 2)
        category = _cell("category", 3)
        note = _cell("note", 4) or None
        layout = _cell("layout", 5) or None

        id_idx = col_map.get("id")
        id_raw = d[id_idx] if id_idx is not None and id_idx < len(d) else ""
        id_raw = id_raw or ""
        sub_id, cat_id = None, None
        if ":" in id_raw and not id_raw.startswith("manual:"):
            parts = id_raw.split(":")
            sub_id, cat_id = parts[0], parts[1]

        estimate_s = item.get("length_t", parse_iso_duration(item["length"]))
        scheduled = parse_horaro_datetime(item["scheduled"])

        setup_s = default_setup_s
        if item.get("options") and item["options"].get("setup"):
            setup_s = parse_iso_duration(f"PT{item['options']['setup'].upper()}")

        items.append(ScheduleItem(
            game=game,
            players=players,
            platform=platform,
            category=category,
            note=note,
            layout=layout,
            submission_id=sub_id,
            category_id=cat_id,
            estimate_seconds=estimate_s,
            scheduled=scheduled,
            setup_seconds=setup_s,
            stream=sched["name"],
        ))

    return Schedule(
        name=sched["name"],
        slug=sched["slug"],
        timezone_str=sched["timezone"],
        start=parse_horaro_datetime(sched["start"]),
        items=items,
    )

"""Slug generation for run briefs.

Produces URL-safe, human-readable slugs for files and directories.
Stream tokens strip the season prefix (e.g. "2026 - Summer (Stream One)" → "stream1").
Game/category slugs are kebab-case, length-capped, with CJK fallback.
"""

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
MAX_SLUG_LENGTH = 60
STREAM_PREFIX_RE = re.compile(r"^\d{4}\s*-\s*\w+\s*\(\s*Stream\s*(\w+)\s*\)$", re.IGNORECASE)
NON_ASCII_RE = re.compile(r"[^\x00-\x7F]")


def _is_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    for ch in text:
        if ord(ch) in range(0x4E00, 0x9FFF + 1):
            return True
        if ord(ch) in range(0x3040, 0x30FF + 1):
            return True
        if ord(ch) in range(0xAC00, 0xD7AF + 1):
            return True
    return False


def _slugify(text: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Convert text to a kebab-case slug. Drops non-ASCII."""
    text = text.lower().strip()

    # Normalize unicode (NFD decomposes accented chars; drop combining marks)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Replace runs of non-alphanumeric with single hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")

    if not text:
        return "untitled"
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def game_slug(game_name: str, submission_id: str = "") -> str:
    """Slug for a game name. Falls back to 'run-<id>' if CJK or empty."""
    if not game_name.strip() or _is_cjk(game_name):
        name = f"run-{submission_id}" if submission_id else "run"
        return name[:MAX_SLUG_LENGTH]
    return _slugify(game_name)


def category_slug(category_name: str) -> str:
    """Slug for a category name. Falls back to 'uncategorized' if empty."""
    if not category_name.strip():
        return "uncategorized"
    return _slugify(category_name)


def run_slug(
    game: str,
    category: str,
    scheduled: datetime,
    submission_id: str = "",
) -> str:
    """Full run slug: <game-slug>__<category-slug>__<YYYY-MM-DDTHHMM>.

    Uniquely identifies a run slot in the schedule.
    """
    gs = game_slug(game, submission_id)
    cs = category_slug(category)
    ts = scheduled.astimezone(TZ).strftime("%Y-%m-%dT%H%M")
    return f"{gs}__{cs}__{ts}"


def stream_token(stream_name: str) -> str:
    """Normalize a full stream name to a short token.

    >>> stream_token("2026 - Summer (Stream One)")
    'stream1'
    >>> stream_token("2026 - Summer (Stream Two)")
    'stream2'
    >>> stream_token("Horaro stream")  # no season prefix
    'horaro-stream'
    """
    m = STREAM_PREFIX_RE.match(stream_name.strip())
    if m:
        word = m.group(1).lower()
        mapping = {"one": "1", "two": "2", "three": "3", "four": "4"}
        return "stream" + mapping.get(word, word)
    return _slugify(stream_name)


def runner_slug(twitch: str, display_name: str, runner_id: int = 0) -> str:
    """Build a runner slug from identity fields.

    Per ADR 0002 (amended): lower(twitch) when present, else
    player-<slugify(display)>-<id>, else player-unknown-<id>.
    The runner_id disambiguator prevents UNIQUE collisions when
    _slugify collapses CJK/empty names to 'untitled'.
    """
    twitch = (twitch or "").strip().lower()
    if twitch:
        return twitch
    display = (display_name or "").strip()
    if display:
        return f"player-{_slugify(display)}-{runner_id}"
    return f"player-unknown-{runner_id}"


def time_token(dt: datetime) -> str:
    """Round a datetime to the nearest hour in Europe/Stockholm.

    Returns HHMM string for directory naming. Minutes/second/microsecond
    are floored (not rounded).

    >>> from datetime import datetime
    >>> dt = datetime(2026, 8, 1, 14, 22, 0, tzinfo=TZ)
    >>> time_token(dt)
    '1400'
    >>> dt2 = datetime(2026, 8, 1, 14, 0, 0, tzinfo=TZ)
    >>> time_token(dt2)
    '1400'
    """
    local = dt.astimezone(TZ)
    floored = local.replace(minute=0, second=0, microsecond=0)
    return floored.strftime("%H%M")


def shift_dir_slug(
    start: datetime,
    end: datetime,
    stream_name: str = "",
) -> str:
    """Directory slug for a shift: YYYY-MM-DD_HHMM-HHMM[_stream-token].

    Rounded to hour for stability across invocations. Date always included.
    Stream token appended when non-default.
    """
    local_start = start.astimezone(TZ)
    local_end = end.astimezone(TZ)

    start_hour = local_start.replace(minute=0, second=0, microsecond=0)
    end_hour = local_end.replace(minute=0, second=0, microsecond=0)
    if end_hour <= start_hour:
        end_hour = start_hour

    date_part = start_hour.strftime("%Y-%m-%d")
    time_part = f"{start_hour.strftime('%H%M')}-{end_hour.strftime('%H%M')}"

    slug = f"{date_part}_{time_part}"
    if stream_name:
        st = stream_token(stream_name)
        slug += f"_{st}"
    return slug

"""Incentive text parsing and analysis.

Conservative auto-split of freeform incentive text into individual incentives.
Extracts time estimates and guesses workflow status.
Validates incentives against the scheduled game to filter out noise.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class IncentiveRow:
    scheduled: datetime
    game: str
    category: str
    stream: str
    runner_display: str
    runner_twitch: str
    runner_discord: str
    incentive_text: str
    details: str = ""
    incentive_category: str = ""
    valid_for_game: str = ""
    incentive_estimate: str = ""
    needs_approval: str = ""
    status: str = ""
    submission_id: str = ""
    row_uuid: str = ""
    flagged_noise: bool = False
    participants: list[dict] = field(default_factory=list)


def split_incentives(text: str) -> list[str]:
    """Conservative auto-split of incentive text into individual items."""
    if not text or text.lower().strip() in ("nada", "no", "none", ""):
        return []

    text = text.strip()

    numbered = re.split(r"\n\s*(?=\d+[\)\.]\s)", text)
    if len(numbered) > 1:
        return [s.strip() for s in numbered if s.strip()]

    bullets = re.split(r"\n\s*(?=[\-\*\•]\s)", text)
    if len(bullets) > 1:
        return [s.strip() for s in bullets if s.strip()]

    return [text]


def extract_estimate_minutes(text: str) -> Optional[int]:
    """Extract time estimate from incentive text, returning minutes or None."""
    text_lower = text.lower()

    hh_mm = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if hh_mm:
        hours = int(hh_mm.group(1))
        minutes = int(hh_mm.group(2))
        return hours * 60 + minutes

    minute_words = re.findall(
        r"(?:adds?\s+|about\s+|roughly\s+|approximately\s+|around\s+|~|≈)?"
        r"(\d+)\s*(?:min(?:utes?)?|m(?!\w))",
        text_lower,
    )
    if minute_words:
        return int(minute_words[0])

    plus_min = re.search(r"\+(\d+)\s*(?:min(?:utes?)?|m(?!\w))", text_lower)
    if plus_min:
        return int(plus_min.group(1))

    estimate_min = re.search(r"estimate\s*(?:is\s*)?(\d+)\s*(?:min(?:utes?)?|m(?!\w))", text_lower)
    if estimate_min:
        return int(estimate_min.group(1))

    return None


def _game_keywords(game_name: str) -> set[str]:
    """Extract searchable keywords from a game name for matching in incentive text."""
    text = game_name.lower()
    text = re.sub(r"[:\-\u2014\u2013\']", " ", text)
    words = text.split()
    keywords = {game_name.lower()}
    for w in words:
        if len(w) > 3 and w not in {"the", "and", "for", "with", "from", "this"}:
            keywords.add(w)
    return keywords


def _extract_mentioned_games(text: str) -> list[str]:
    """Find capitalized game-name-like phrases in text (Title Case or ALL CAPS words)."""
    matches = re.findall(
        r"(?:^|[\n:,;/])([A-Z][A-Za-z0-9' &]+(?:\s+[A-Z][A-Za-z0-9' &]+){0,4})",
        text,
    )
    cleaned = []
    stop = {"The", "A", "An", "If", "For", "And", "But", "In", "On", "At", "By",
            "To", "With", "From", "Or", "Not", "We", "I", "You", "They", "He", "She",
            "It", "This", "That", "These", "Those", "My", "Our", "Your", "His", "Her",
            "After", "Before", "During", "While", "Can", "Could", "Will", "Would",
            "Should", "May", "Might", "Must", "Do", "Does", "Did", "Has", "Have", "Had",
            "Game", "Run", "Category", "Estimate", "Time", "Add", "Adds", "Added",
            "Could", "Would", "Please", "Thanks", "Thank", "Also", "Plus", "Minus",
            "Using", "Used", "Make", "Makes", "Made", "Get", "Gets", "Got",
            "Standard", "Bonus", "Choose", "Chosen", "Select", "Selected",
            "One", "Two", "Three", "First", "Second", "Third", "Last", "Next",
            "New", "Old", "Other", "Some", "Any", "All", "Each", "Every"}
    for m in matches:
        m = m.strip()
        if not m or m[0].islower():
            continue
        first_word = m.split()[0] if m.split() else ""
        if first_word in stop:
            continue
        if len(m) < 3:
            continue
        if m.isupper() and len(m.split()) == 1:
            continue
        cleaned.append(m)
    return cleaned


def validate_incentive_for_game(
    scheduled_game: str,
    runner_other_games: list[str],
    incentive_text: str,
) -> str:
    """Check if an incentive is related to the scheduled game.

    Returns:
        "Valid" — clearly about the scheduled game
        "Invalid" — about a different game the runner submitted (noise, filter out)
        "Needs Review" — ambiguous, can't determine
    """
    text_lower = incentive_text.lower()
    scheduled_kw = _game_keywords(scheduled_game)
    other_games = [g for g in runner_other_games if g.lower() != scheduled_game.lower()]

    scheduled_match = any(kw in text_lower for kw in scheduled_kw if len(kw) > 2)

    mentioned = _extract_mentioned_games(incentive_text)
    mentioned_lower = [m.lower() for m in mentioned]

    other_game_mentioned = False
    for other in other_games:
        other_kw = _game_keywords(other)
        for kw in other_kw:
            if len(kw) > 3 and kw in text_lower:
                if not any(kw in ml for ml in mentioned_lower if kw in ml):
                    other_game_mentioned = True
                    break
        if other_game_mentioned:
            break

    if scheduled_match and not other_game_mentioned:
        return "Valid"
    if other_game_mentioned and not scheduled_match:
        return "Invalid"
    if scheduled_match and other_game_mentioned:
        return "Valid"
    return "Needs Review"


def guess_status(
    category: str,
    valid_for_game: str,
    estimate: str,
    existing_status: str = "",
) -> str:
    """Guess the workflow status based on other column values."""
    if existing_status == "Removed":
        return "Removed"
    if existing_status == "Approved":
        return "Approved"

    if not category:
        return "To-Do"

    if valid_for_game == "Needs Review" or estimate == "Unknown":
        return "Needs Information"

    if category and valid_for_game == "Yes" and estimate and estimate != "Unknown":
        return "In Review"

    return "To-Do"


def generate_uuid() -> str:
    return str(uuid.uuid4())


def _normalise(text: str) -> str:
    """Normalise incentive text for deduplication."""
    return re.sub(r"\s+", " ", text).strip().lower()


def build_incentive_rows(
    xref_rows: list,
    existing_incentives: dict[str, dict] = None,
    runner_games_map: dict[str, list[str]] = None,
) -> list[IncentiveRow]:
    """Build IncentiveRow list from cross-reference data.

    Auto-splits incentive text, extracts estimates, validates against
    scheduled game, guesses status. Preserves existing annotations by
    UUID when re-running.

    For multi-runner (race) rows, incentive texts from all race-linked
    submissions are unioned and deduped by normalised text before splitting.
    """
    if existing_incentives is None:
        existing_incentives = {}
    if runner_games_map is None:
        runner_games_map = {}

    rows = []
    for xr in xref_rows:
        if not xr.incentives or xr.incentives.lower().strip() in ("nada", "no", "none", ""):
            continue

        # Gather other-games from all race-linked submissions for noise detection.
        other_games: list[str] = []
        seen_games: set[str] = set()
        for sid in (getattr(xr, "runner_submission_ids", None) or [xr.submission_id or ""]):
            for g in runner_games_map.get(str(sid), []):
                if g not in seen_games:
                    seen_games.add(g)
                    other_games.append(g)

        # Split the already-unioned incentives text (xr.incentives was pre-merged
        # in _build_cross_reference for race rows).
        texts = split_incentives(xr.incentives)

        # Dedupe across splits by normalised text (rare edge where the union
        # didn't fully dedupe due to whitespace differences).
        seen_norms: set[str] = set()
        deduped: list[str] = []
        for t in texts:
            n = _normalise(t)
            if n not in seen_norms:
                seen_norms.add(n)
                deduped.append(t)

        for text in deduped:
            est_min = extract_estimate_minutes(text)
            estimate_str = str(est_min) if est_min is not None else "Unknown"
            needs_approval = "Yes" if (est_min is None or est_min >= 15) else "No"

            row_uuid = generate_uuid()
            category = ""
            valid = ""
            status = ""
            details = ""
            flagged = False

            if row_uuid in existing_incentives:
                prev = existing_incentives[row_uuid]
                category = prev.get("category", "")
                valid = prev.get("valid_for_game", "")
                estimate_str = prev.get("estimate", estimate_str)
                status = prev.get("status", "")
                details = prev.get("details", "")
                if prev.get("text"):
                    text = prev["text"]
            else:
                validation = validate_incentive_for_game(
                    xr.game, other_games, text
                )
                if validation == "Valid":
                    valid = "Yes"
                elif validation == "Invalid":
                    valid = "No"
                    flagged = True
                else:
                    valid = "Needs Review"

            status = guess_status(category, valid, estimate_str, status)

            participants = getattr(xr, "participants", None) or []

            rows.append(IncentiveRow(
                scheduled=xr.scheduled,
                game=xr.game,
                category=xr.category,
                stream=xr.stream,
                runner_display=xr.runner_display,
                runner_twitch=xr.runner_twitch,
                runner_discord=xr.runner_discord,
                incentive_text=text,
                details=details,
                incentive_category=category,
                valid_for_game=valid,
                incentive_estimate=estimate_str,
                needs_approval=needs_approval,
                status=status,
                submission_id=xr.submission_id or "",
                row_uuid=row_uuid,
                flagged_noise=flagged,
                participants=participants,
            ))

    return rows

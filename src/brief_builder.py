"""Brief builder — assembles markdown briefs and JSON sidecars from run data.

Used by src/brief.py's generate_briefs() (admin sync endpoint) and
by the CLI cmd_write subcommand.  build_brief() is the single entry
point: given a RunRow and pre-loaded context data, it returns
(md_content, json_data).

DB-primary:  Pass ``incentives`` and ``all_runs`` loaded from the DB
(via xlsx_reader.read_incentives_from_db / read_cross_reference_from_db).

xlsx shim:   If ``incentives`` / ``all_runs`` are omitted the function
falls back to reading them from ``spreadsheet_path`` so existing callers
continue to work.  This shim will be removed when xlsx is retired.
See: https://github.com/anomalyco/esa-waypoint/issues (xlsx→CSV migration)
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import xlsx_reader as xr
from .slugs import run_slug
from .src_api import (
    SrcApiError,
    fetch_category_wr,
    fetch_game_records,
    fetch_src_categories,
    search_src_game,
    search_user_by_lookup,
)

TZ = ZoneInfo("Europe/Stockholm")


def seconds_to_hms(sec: Any) -> str:
    """Format a seconds value as a smart speedrun time string.

    Omits the hours component when the time is under one hour:
        98307  -> "1:21:47"
        2307   -> "38:27"
        5907.0 -> "1:38:27"
        None   -> "?"
    """
    try:
        total = int(float(sec))
    except (TypeError, ValueError):
        return "?"
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_brief(
    run_row: xr.RunRow,
    spreadsheet_path: str = "",
    *,
    incentives: Optional[list[xr.IncentiveRow]] = None,
    all_runs: Optional[list[xr.RunRow]] = None,
) -> tuple[str, dict]:
    """Build a markdown brief + JSON sidecar for a single run.

    Args:
        run_row: The run to brief.
        spreadsheet_path: Path to xlsx (used only when ``incentives`` /
            ``all_runs`` are not supplied — xlsx shim, deprecated).
        incentives: Pre-loaded incentive rows (DB-primary path).
        all_runs: Pre-loaded schedule rows for sibling lookup (DB-primary path).

    Returns:
        (md_content, json_data)

    Errors from SRC lookups are captured in the sidecar under
    ``errors`` — they never propagate.
    """
    md_parts: list[str] = []
    json_data: dict[str, Any] = {
        "slug": "",
        "scheduled": run_row.scheduled.isoformat() if run_row.scheduled else "",
        "mode": "scan",
        "run_meta": _build_run_meta(run_row),
        "incentives": _build_incentives(run_row, spreadsheet_path, incentives=incentives),
        "runner_section": None,
        "category_section": None,
        "game_section": None,
        "interview_material": [],
        "siblings": [],
        "sources": [],
        "confidence_flags": [],
        "errors": [],
    }

    slug = run_slug(
        run_row.game,
        run_row.category,
        run_row.scheduled,
        run_row.submission_id or "",
    )
    json_data["slug"] = slug

    _add_game_and_category_info(run_row, json_data, md_parts)
    _add_runner_info(run_row, json_data, md_parts)
    _add_siblings_to_sidecar(run_row, spreadsheet_path, json_data, all_runs=all_runs)

    md_parts.insert(0, f"# {run_row.game} — {run_row.category}\n\n")
    md_parts.append(_build_sources_section(json_data["sources"], json_data.get("confidence_flags", [])))

    md_content = "\n".join(md_parts)
    return md_content.strip(), json_data


def _build_run_meta(run_row: xr.RunRow) -> dict:
    participants = []
    if run_row.participants:
        participants = run_row.participants
    elif run_row.runner_display:
        participants.append({
            "name": run_row.runner_display,
            "twitch": run_row.runner_twitch or "",
            "discord": run_row.runner_discord or "",
            "twitter": run_row.runner_twitter or "",
        })

    return {
        "pick": run_row.pick,
        "scheduled": run_row.scheduled.isoformat() if run_row.scheduled else "",
        "game": run_row.game,
        "category": run_row.category,
        "estimate": run_row.estimate,
        "platform": run_row.platform or "",
        "stream": run_row.stream,
        "stream_short": xr.stream_token_to_short(run_row.stream) if hasattr(xr, "stream_token_to_short") else run_row.stream,
        "participants": participants,
        "commentator": run_row.commentator or "",
        "pronouns": run_row.pronouns or "",
        "show_cam": run_row.show_cam or "",
        "submission_id": run_row.submission_id or "",
        "layout": run_row.layout or "",
        "note": run_row.note or "",
    }


def _build_incentives(
    run_row: xr.RunRow,
    spreadsheet_path: str = "",
    *,
    incentives: Optional[list[xr.IncentiveRow]] = None,
) -> list[dict]:
    """Build a list of incentive dicts for the sidecar.

    Uses ``incentives`` if provided (DB-primary), otherwise falls back to
    reading from ``spreadsheet_path`` (xlsx shim).
    """
    result: list[dict] = []

    if incentives is None:
        # xlsx shim — deprecated path
        try:
            incentives = xr.read_incentives(spreadsheet_path)
        except Exception:
            return result

    run_scheduled = run_row.scheduled
    if isinstance(run_scheduled, datetime) and not run_scheduled.tzinfo:
        run_scheduled = run_scheduled.replace(tzinfo=TZ)

    for inv in incentives:
        inv_scheduled = inv.scheduled
        if isinstance(inv_scheduled, datetime) and not inv_scheduled.tzinfo:
            inv_scheduled = inv_scheduled.replace(tzinfo=TZ)
        if inv_scheduled != run_scheduled:
            continue
        if inv.game != run_row.game:
            continue
        if inv.category != run_row.category:
            continue

        result.append({
            "uuid": inv.uuid or "",
            "category": inv.incentive_category or "",
            "description": inv.incentive_text or "",
            "details": inv.details or "",
            "estimate": inv.incentive_estimate or "",
            "valid_for_game": inv.valid_for_game or "",
            "status": inv.status or "",
            "needs_approval": inv.needs_approval or "",
        })

    return result


def _add_game_and_category_info(
    run_row: xr.RunRow,
    json_data: dict,
    md_parts: list[str],
) -> None:
    game_name = run_row.game
    category_name = run_row.category

    game = search_src_game(game_name)
    if not game:
        json_data["confidence_flags"].append(f"SRC game not found for '{game_name}'")
        return

    game_id = game["id"]
    abbr = game.get("abbreviation", "")
    src_url = f"https://www.speedrun.com/{abbr}" if abbr else ""

    json_data["game_section"] = {
        "name": (game.get("names", {}) or {}).get("international", "") or game_name,
        "abbreviation": abbr,
        "src_url": src_url,
    }
    json_data["sources"].append({"name": "speedrun.com", "url": src_url})
    md_parts.append(f"SRC: [{abbr}]({src_url})  \n")

    matching_cat = None
    try:
        cats = fetch_src_categories(game_id)
        for c in cats:
            if c["name"].lower() == category_name.lower():
                matching_cat = c
                break
        if matching_cat:
            md_parts.append(f"Category type: {matching_cat.get('type', '')}  \n")
        else:
            json_data["confidence_flags"].append(
                f"Category '{category_name}' not found on SRC — records may cover wrong category"
            )
    except SrcApiError:
        json_data["confidence_flags"].append("Could not fetch SRC categories")

    try:
        all_records = fetch_game_records(game_id)
        # Filter to the matched category so we don't show records for the wrong category.
        if matching_cat:
            cat_id = matching_cat["id"]
            cat_records = [r for r in all_records if r.get("category_id") == cat_id]
        else:
            # No category match — fall back to all records with a flag already set above.
            cat_records = all_records

        if cat_records:
            normalized = []
            for i, rec in enumerate(cat_records):
                wr_sec = rec.get("wr_seconds")
                time_str = seconds_to_hms(wr_sec)
                normalized.append({
                    "place": i + 1,
                    "runner": rec.get("runner_name") or rec.get("runner_id") or "?",
                    "time": time_str,
                    "date": rec.get("date") or "",
                })
            json_data["category_section"] = {
                "name": category_name,
                "records": normalized,
            }
            wr = normalized[0] if normalized else None
            if wr:
                md_parts.append(f"**WR:** {wr.get('runner', '?')} — {wr.get('time', '?')} ({wr.get('date', '?')})  \n")
    except SrcApiError:
        json_data["confidence_flags"].append("Could not fetch SRC records")


def _add_runner_info(
    run_row: xr.RunRow,
    json_data: dict,
    md_parts: list[str],
) -> None:
    """Add runner identity to the run brief.

    Only records identity (name, twitch, SRC url, verified flag) — no PBs,
    no ESA history, no communities, no country.  Runner history lives on the
    runner profile page and must not be duplicated in the run brief.
    """
    names_to_try: list[tuple[str, str]] = []
    if run_row.participants:
        for p in run_row.participants:
            nm = p.get("name") or p.get("display") or ""
            tw = p.get("twitch") or ""
            if nm or tw:
                names_to_try.append((nm, tw))
    if run_row.runner_display or run_row.runner_twitch:
        names_to_try.append((run_row.runner_display, run_row.runner_twitch))

    if not names_to_try:
        return

    first_name, first_twitch = names_to_try[0]
    display_name = first_name or first_twitch or "Runner"

    user = None
    try:
        if first_twitch:
            user = search_user_by_lookup(first_twitch)
        if not user and first_name:
            user = search_user_by_lookup(first_name)
    except SrcApiError:
        pass

    if user:
        user_name = (user.get("names", {}) or {}).get("international", "")
        src_url = f"https://www.speedrun.com/users/{user_name}" if user_name else None

        if src_url:
            json_data["sources"].append({"name": "speedrun.com", "url": src_url})

        # Identity only — PBs / history belong on the runner page, not here.
        json_data["runner_section"] = {
            "name": user_name or display_name,
            "twitch": first_twitch,
            "src_url": src_url,
            "verified": True,
        }
        md_parts.append(f"**Runner:** [{user_name or display_name}]({src_url})  \n")
    else:
        json_data["runner_section"] = {
            "name": display_name,
            "twitch": first_twitch,
            "src_url": None,
            "verified": False,
        }
        md_parts.append(f"**Runner:** {display_name}  \n")
        json_data["confidence_flags"].append(f"Runner '{display_name}' not verified on SRC")


def _add_siblings_to_sidecar(
    run_row: xr.RunRow,
    spreadsheet_path: str = "",
    json_data: dict = None,
    *,
    all_runs: Optional[list[xr.RunRow]] = None,
) -> None:
    """Add sibling runs to the sidecar.

    Uses ``all_runs`` if provided (DB-primary), otherwise falls back to
    reading from ``spreadsheet_path`` (xlsx shim).
    """
    if json_data is None:
        json_data = {}

    if all_runs is None:
        # xlsx shim — deprecated path
        try:
            all_runs = xr.read_cross_reference(spreadsheet_path)
        except Exception:
            return

    siblings = xr.find_runner_sibling_runs(
        runs=all_runs,
        twitch=run_row.runner_twitch,
        display_name=run_row.runner_display,
        exclude_submission_id=run_row.submission_id or "",
    )
    # Normalize: find_runner_sibling_runs returns {total, runs} dict; flatten to list
    if isinstance(siblings, dict):
        siblings = siblings.get("runs") or []
    if siblings:
        json_data["siblings"] = siblings


def _build_sources_section(
    sources: list[dict],
    confidence_flags: list[str],
) -> str:
    parts = ["\n## Sources"]
    for s in sources:
        name = s.get("name", "")
        url = s.get("url", "")
        if url:
            parts.append(f"- [{name}]({url})")
        else:
            parts.append(f"- {name}")
    for flag in confidence_flags:
        parts.append(f"- ⚠ {flag}")
    return "\n".join(parts)

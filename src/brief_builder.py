"""Brief builder — assembles markdown briefs and JSON sidecars from run data.

Used by src/brief.py's generate_briefs() (admin sync endpoint) and
by the CLI cmd_write subcommand.  build_brief() is the single entry
point: given a RunRow and a spreadsheet path, it returns
(md_content, json_data).
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any
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
    fetch_user_profile,
    fetch_user_personal_bests,
)

TZ = ZoneInfo("Europe/Stockholm")


def build_brief(
    run_row: xr.RunRow,
    spreadsheet_path: str,
) -> tuple[str, dict]:
    """Build a markdown brief + JSON sidecar for a single run.

    Returns (md_content, json_data).

    Errors from SRC lookups are captured in the sidecar under
    ``errors`` — they never propagate.
    """
    md_parts: list[str] = []
    json_data: dict[str, Any] = {
        "slug": "",
        "scheduled": run_row.scheduled.isoformat() if run_row.scheduled else "",
        "mode": "scan",
        "run_meta": _build_run_meta(run_row),
        "incentives": _build_incentives(run_row, spreadsheet_path),
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
    _add_siblings_to_sidecar(run_row, spreadsheet_path, json_data)

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


def _build_incentives(run_row: xr.RunRow, spreadsheet_path: str) -> list[dict]:
    """Build a list of incentive dicts for the sidecar."""
    result: list[dict] = []
    try:
        incentives = xr.read_incentives(spreadsheet_path)
    except Exception:
        return result

    now = datetime.now(TZ)
    for inv in incentives:
        inv_scheduled = inv.scheduled
        if isinstance(inv_scheduled, datetime) and not inv_scheduled.tzinfo:
            inv_scheduled = inv_scheduled.replace(tzinfo=TZ)
        if inv_scheduled != run_row.scheduled:
            continue
        if inv.game != run_row.game:
            continue
        if inv.category != run_row.category:
            continue

        result.append({
            "uuid": inv.uuid or "",
            "category": inv.incentive_category or "",
            "description": inv.incentive_text or "",
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

    try:
        cats = fetch_src_categories(game_id)
        matching_cat = None
        for c in cats:
            if c["name"].lower() == category_name.lower():
                matching_cat = c
                break
        if matching_cat:
            md_parts.append(f"Category type: {matching_cat.get('type', '')}  \n")
    except SrcApiError:
        json_data["confidence_flags"].append("Could not fetch SRC categories")

    try:
        records = fetch_game_records(game_id)
        if records:
            json_data["category_section"] = {
                "name": category_name,
                "records": records,
            }
            wr = records[0] if records else None
            if wr:
                md_parts.append(f"**WR:** {wr.get('runner', '?')} — {wr.get('time', '?')} ({wr.get('date', '?')})  \n")
    except SrcApiError:
        json_data["confidence_flags"].append("Could not fetch SRC records")


def _add_runner_info(
    run_row: xr.RunRow,
    json_data: dict,
    md_parts: list[str],
) -> None:
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
        user_id = user.get("id", "")
        user_name = (user.get("names", {}) or {}).get("international", "")
        user_twitch_uri = (user.get("twitch", {}) or {}).get("uri", "") if user.get("twitch") else ""
        src_url = f"https://www.speedrun.com/users/{user_name}" if user_name else None

        if src_url:
            json_data["sources"].append({"name": "speedrun.com", "url": src_url})

        try:
            profile = fetch_user_profile(user_id)
        except SrcApiError:
            profile = None

        try:
            pbs = fetch_user_personal_bests(user_id)
            pb_count = len(pbs)
            pb_games = list(dict.fromkeys(p["game_name"] for p in pbs))[:5]
        except (SrcApiError, Exception):
            pb_count = 0
            pb_games = []

        runner_info = {
            "name": user_name or display_name,
            "twitch": first_twitch,
            "src_url": src_url,
            "verified": True,
            "pb_count": pb_count,
            "top_games": pb_games,
        }
        json_data["runner_section"] = runner_info
        md_parts.append(f"**Runner:** [{user_name or display_name}]({src_url})  \n")
        if pb_count:
            games_str = ", ".join(pb_games)
            md_parts.append(f"**PBs:** {pb_count} across {games_str}  \n")
    else:
        json_data["runner_section"] = {
            "name": display_name,
            "twitch": first_twitch,
            "src_url": None,
            "verified": False,
            "pb_count": 0,
            "top_games": [],
        }
        md_parts.append(f"**Runner:** {display_name}  \n")
        json_data["confidence_flags"].append(f"Runner '{display_name}' not verified on SRC")


def _add_siblings_to_sidecar(
    run_row: xr.RunRow,
    spreadsheet_path: str,
    json_data: dict,
) -> None:
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
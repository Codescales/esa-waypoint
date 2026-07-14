"""Prompt templates for LLM-authored run briefs.

The LLM's job is to write the *prose* only — the structured sidecar
(incentives, siblings, sources, confidence_flags) is assembled
deterministically by brief_builder.py and passed in as context.

Run briefs cover the RUN: game, category, world record, incentives,
what to watch. Runner history (ESA appearances, SRC tenure, communities,
country, PBs) lives on the runner profile page and must NOT appear here.

Three modes:
    scan       Fast overview; what a host needs in 60 seconds.
    interview  Expanded game/category context + talking points.
    full       All run-relevant sections at full depth.
"""

import json
from typing import Any

SYSTEM_PROMPT = """\
You are an expert marathon host briefing writer for ESA (European Speedrun Assembly).
Your job is to write concise, accurate, host-ready markdown briefs for speedruns.

Rules:
- Write about the RUN: the game, category, world record, strats, incentives, what to watch.
- Do NOT write about the runner's history, ESA appearances, SRC tenure, communities, country,
  or personal bests. That information lives on the runner profile page.
- You may mention the runner's name and link once as identification only.
- Never fabricate facts. If data is missing, say so briefly.
- Do NOT reproduce the raw JSON or repeat every field verbatim — synthesise it.
- Do NOT include a Sources section — that is added separately.
- Do NOT include incentives verbatim in the prose — they appear in a separate panel.
- Headings use ## (h2). Keep the brief scannable.
- Confidence flags from the sidecar should be mentioned where relevant.
- Output markdown only. No preamble, no closing remarks.
"""


def _fmt_incentives(incentives: list[dict]) -> str:
    if not incentives:
        return "None."
    lines = []
    for inv in incentives:
        desc = inv.get("description") or inv.get("incentive_text") or ""
        cat = inv.get("category") or ""
        est = inv.get("estimate") or ""
        status = inv.get("status") or ""
        line = f"- [{cat}] {desc}"
        if est:
            line += f" (est: {est})"
        if status and status.lower() not in ("", "pending"):
            line += f" [{status}]"
        lines.append(line)
    return "\n".join(lines)


def _fmt_siblings(siblings) -> str:
    # siblings may be a list of dicts or a {total, runs} dict from find_runner_sibling_runs
    if isinstance(siblings, dict):
        siblings = siblings.get("runs") or []
    if not siblings:
        return "None."
    lines = []
    for sib in siblings:
        game = sib.get("game", "")
        cat = sib.get("category", "")
        sched = sib.get("scheduled", "")
        stream = sib.get("stream", "")
        is_next = sib.get("is_next", False)
        marker = " [NEXT]" if is_next else ""
        lines.append(f"- {game} — {cat} @ {sched} ({stream}){marker}")
    return "\n".join(lines)


def _fmt_records(records: list[dict]) -> str:
    if not records:
        return "No records found."
    lines = []
    for r in records[:5]:
        place = r.get("place", "?")
        runner = r.get("runner", "?")
        time = r.get("time", "?")
        date = r.get("date", "")
        line = f"#{place} {runner} — {time}"
        if date:
            line += f" ({date})"
        lines.append(line)
    return "\n".join(lines)


def build_user_prompt(
    *,
    mode: str,
    run_meta: dict,
    sidecar: dict,
) -> str:
    """Build the user-turn prompt for a given run and mode.

    Args:
        mode: "scan" | "interview" | "full"
        run_meta: The run_meta dict from the sidecar.
        sidecar: The full deterministic sidecar JSON dict.

    Returns:
        The user-turn prompt string.
    """
    game = run_meta.get("game", "")
    category = run_meta.get("category", "")
    estimate = run_meta.get("estimate", "")
    platform = run_meta.get("platform", "")
    stream = run_meta.get("stream", "")
    scheduled = run_meta.get("scheduled", "")

    participants = run_meta.get("participants") or []
    runner_names = ", ".join(
        p.get("name") or p.get("display") or p.get("twitch") or "Unknown"
        for p in participants
    ) or run_meta.get("runner_display", "Unknown")

    runner_section = sidecar.get("runner_section") or {}
    category_section = sidecar.get("category_section") or {}
    game_section = sidecar.get("game_section") or {}
    confidence_flags = sidecar.get("confidence_flags") or []

    records_str = _fmt_records(category_section.get("records") or [])
    incentives_str = _fmt_incentives(sidecar.get("incentives") or [])
    siblings_str = _fmt_siblings(sidecar.get("siblings") or [])

    flags_str = ""
    if confidence_flags:
        flags_str = "\nConfidence flags:\n" + "\n".join(f"- ⚠ {f}" for f in confidence_flags)

    base = f"""\
Write a host brief for the following speedrun.

## Run details
Game: {game}
Category: {category}
Runner(s): {runner_names} (identity only — do not write their history)
SRC profile: {runner_section.get("src_url") or "N/A"}
Estimate: {estimate}
Platform: {platform or "N/A"}
Stream: {stream}
Scheduled: {scheduled}

## Game on SRC
{game_section.get("name", game)} ({game_section.get("abbreviation", "")})
URL: {game_section.get("src_url", "N/A")}

## Category records
{records_str}

## Incentives (for context — do NOT reproduce verbatim in the brief)
{incentives_str}

## Same-runner runs in this marathon
{siblings_str}
{flags_str}"""

    if mode == "scan":
        return base + """

Write a scan brief: a short, punchy overview for hosts who have 60 seconds.
Sections to include (##):
- Game Overview (2–3 sentences: genre, speedrun community, why it's interesting)
- Category & World Record (what the category involves, current WR holder and time)
- Things to Watch (2–3 notable moments, skips, tricks, or viewer hooks)

Keep each section to 2–4 sentences. Total length: ~200–300 words.
Mention the runner's name once to identify who is running. No runner history.
"""

    if mode == "interview":
        return base + """

Write an interview brief: expanded context for a host conducting an on-air conversation.
Focus entirely on the game and category. No runner biography.
Sections to include (##):
- Game Overview (history, developer, why this game has a speedrun community)
- Category Deep-Dive (what the category requires, major tricks/skips/strats, rule nuances)
- World Record & Leaderboard (WR context, how competitive the board is)
- Talking Points (4–5 concrete topics the host can explore on air about the game/category)
- Things to Watch (key moments, emotional beats, viewer hooks specific to this category)

Target length: ~400–500 words.
"""

    # full
    return base + """

Write a full-depth brief covering everything a host might need for a long segment.
Focus on the game and category. No runner biography.
Sections to include (##):
- Game Overview
- Category & Rules (full explanation: what counts, major route choices, banned techniques)
- World Record & Leaderboard (top 3–5 times, WR progression if notable)
- Marathon Context (incentives and sibling runs the host should set up naturally)
- Talking Points (5+ topics drawn from the game, category, or incentives)
- Things to Watch (key moments in the run ordered by rough timing if possible)

Target length: ~600–800 words.
"""

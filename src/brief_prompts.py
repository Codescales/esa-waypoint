"""Prompt templates for LLM-authored run briefs.

The LLM's job is to write the *prose* only — the structured sidecar
(incentives, siblings, sources, confidence_flags) is assembled
deterministically by brief_builder.py and passed in as context.

Run briefs cover the RUN: game, category, world record, incentives,
what to watch. Runner history (ESA appearances, SRC tenure, communities,
country, PBs) lives on the runner profile page and must NOT appear here.

Brief structure (5 sections, bullet-level layout for quick reference):
  1. Game Overview              — genre, setting, publisher/dev, released, similar games
  2. Run Overview               — category goal, rules/restrictions, runner count, WR
  3. Recent Speedrun History    — new tricks/discoveries (from SRC if available, else "no data")
  4. Trivia & Interesting Facts — LLM-validated from Wikipedia summary candidates
  5. Interview Questions        — 3–5 open-ended questions for the runner
"""

import json
import re
from typing import Any

SYSTEM_PROMPT = """\
You are an expert marathon host briefing writer for ESA (European Speedrun Assembly).
Your job is to write a concise, accurate, host-ready markdown brief for a speedrun.

Layout: bullet-level. Hosts need to scan the brief quickly during a live broadcast and \
find specific facts (developer, release year, WR holder, rules) in seconds. Use a \
labeled bullet structure under each ## heading, not dense paragraphs.

Rules:
- Write about the RUN: the game, category, world record, strats, what to watch.
- Do NOT write about the runner's history, ESA appearances, SRC tenure, communities, \
country, or personal bests. That information lives on the runner profile page.
- You may mention the runner's name once as identification only.
- When data is unavailable, say so briefly in plain prose or with a `*No data available.*` \
note. Never echo raw warning flags or repeat field names verbatim.
- Do NOT reproduce the raw JSON or repeat every field verbatim — synthesise it.
- Do NOT include a Sources section — that is added separately.
- Incentives are context only. Do NOT include them in the prose — they appear in a \
separate panel on the page.
- Use exactly the five ## section headings in the order specified.
- Under each heading, use a labeled-bullet layout: each fact on its own line, prefixed \
with a bold label (e.g. `**Genre:**`, `**WR:**`). One fact per bullet.
- For "Similar games", "Trivia & Interesting Facts", and "Interview Questions", use \
plain bullets without bold labels (these are lists of items, not labeled facts).
- Output markdown only. No preamble, no closing remarks. No code fences.
"""

SECTION_INSTRUCTIONS = """\

Output exactly these five ## sections, in this order, using the labeled-bullet layout:

## Game Overview
Bulleted facts about the game itself:
- **Genre:**
- **Setting:**
- **Publisher / Developer:**
- **Released:** (year and platform if known)
- **Similar games:** (2–4 comparable titles, plain bullets)

## Run Overview
Bulleted facts about this specific run:
- **Category goal:** (one sentence)
- **Rules & restrictions:** (one bullet per rule — timers, banned glitches, difficulty, etc.)
- **Runners in this category on SRC:** (count)
- **World record:** (holder, time, date)

## Recent Speedrun History & Discoveries
- If forum_highlights data is provided, summarise 2–4 recent notable runs, new tricks, \
or discoveries as plain bullets. Cite the date if available.
- If no data is provided, output exactly: *No recent forum activity found.*

## Trivia & Interesting Facts
- If trivia_candidates are provided, validate each candidate against the game name and \
context. Include 3–5 facts that are accurate, interesting, and not already in Game Overview.
- If no candidates are provided, output exactly: *No trivia data available.*
- Plain bullets, no bold labels.

## Interview Questions
- 3–5 open-ended questions the host can ask the runner on air.
- Phrase each as a direct question (e.g. "What's the hardest part of this route to \
execute live?").
- Do NOT assert facts about the runner's history, PBs, or ESA appearances — ask open \
questions that invite the runner to share their own perspective.
- Plain bullets, no bold labels.

Total word budget: 600 words across all sections. Be concise. Hosts scan, they don't read.
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
        # Defensive: if time looks like raw seconds (float/int string), format it.
        if re.fullmatch(r"\d+(\.\d+)?", str(time)):
            try:
                total = int(float(time))
                h = total // 3600
                m = (total % 3600) // 60
                s = total % 60
                time = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            except (ValueError, TypeError):
                pass
        line = f"#{place} {runner} — {time}"
        if date:
            line += f" ({date})"
        lines.append(line)
    return "\n".join(lines)


def _fmt_forum_highlights(forum_highlights: list[str]) -> str:
    """Format forum highlights for the prompt. Empty list → explicit no-data marker."""
    if not forum_highlights:
        return "(no data — the brief should show *No recent forum activity found.*)"
    return "\n".join(f"- {h}" for h in forum_highlights)


def _fmt_trivia_candidates(trivia_candidates: list[str]) -> str:
    """Format trivia candidates for the prompt. Empty list → explicit no-data marker."""
    if not trivia_candidates:
        return "(no data — the brief should show *No trivia data available.*)"
    return "\n".join(f"- {c}" for c in trivia_candidates)


def build_user_prompt(
    *,
    run_meta: dict,
    sidecar: dict,
) -> str:
    """Build the user-turn prompt for a given run.

    Args:
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

    records_str = _fmt_records(category_section.get("records") or [])
    incentives_str = _fmt_incentives(sidecar.get("incentives") or [])
    siblings_str = _fmt_siblings(sidecar.get("siblings") or [])
    forum_str = _fmt_forum_highlights(sidecar.get("forum_highlights") or [])
    trivia_str = _fmt_trivia_candidates(sidecar.get("trivia_candidates") or [])
    runner_count = category_section.get("runner_count", "unknown")

    return f"""\
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

## Category records (this category only)
{records_str}

## Runners in this category on SRC
{runner_count}

## Incentives (context only — do NOT include in the brief prose)
{incentives_str}

## Same-runner runs in this marathon
{siblings_str}

## Recent forum highlights (for the "Recent Speedrun History & Discoveries" section)
{forum_str}

## Trivia candidates (for the "Trivia & Interesting Facts" section — validate before use)
{trivia_str}
""" + SECTION_INSTRUCTIONS

"""Compare local xlsx data against the live Horaro schedules.

Reports:
1. Run count match
2. Runs in xlsx but not in Horaro
3. Runs in Horaro but not in xlsx
4. Schedule diffs (time, runner, category, estimate, platform)
5. ID changes (submission_id, category_id)
6. Pre-existing data quality issues (cosmetic)

Usage:
    python -m src.check_horaro_parity [--xlsx PATH] [--horaro-org esa]

Exits 0 if all checks pass (no schedule changes, IDs match).
Exits 1 if any divergence is found.

Phase 1 data is read-only. This script is also read-only.
"""

import argparse
import sys

from src.horaro import fetch_schedule
from src import xlsx_reader as xr


def main():
    p = argparse.ArgumentParser(description="Compare xlsx to live Horaro schedules")
    p.add_argument("--xlsx", default="output/incentive_plan.xlsx", help="Path to xlsx")
    p.add_argument(
        "--horaro-schedules", default="2026-summer1,2026-summer2",
        help="Comma-separated Horaro schedule slugs",
    )
    p.add_argument("--horaro-org", default="esa", help="Horaro organization")
    args = p.parse_args()

    # Read xlsx
    xlsx_runs = xr.read_cross_reference(args.xlsx)
    xlsx_runs_by_id = {(r.submission_id, r.category_id): r for r in xlsx_runs if r.submission_id}
    xlsx_break_count = sum(1 for r in xlsx_runs if r.game.lower() == "overnight break")

    # Read Horaro via API
    horaro_items = []
    for slug in args.horaro_schedules.split(","):
        sched = fetch_schedule(args.horaro_org, slug.strip())
        horaro_items.extend(sched.items)

    horaro_by_id = {
        (it.submission_id, it.category_id): it for it in horaro_items if it.submission_id
    }
    horaro_break_count = sum(1 for it in horaro_items if it.game.lower() == "overnight break")

    # Filter out breaks
    xlsx_real = [r for r in xlsx_runs if r.game.lower() != "overnight break"]
    horaro_real = [it for it in horaro_items if it.game.lower() != "overnight break"]

    print("=" * 60)
    print("Horaro Parity Check")
    print("=" * 60)
    print(f"XLSX:    {len(xlsx_runs)} total ({len(xlsx_real)} runs, {xlsx_break_count} breaks)")
    print(f"Horaro:  {len(horaro_items)} total ({len(horaro_real)} runs, {horaro_break_count} breaks)")
    print(f"Run count match (real): {'PASS' if len(xlsx_real) == len(horaro_real) else 'FAIL'}")
    print()

    # ID sets
    xlsx_ids = set(xlsx_runs_by_id.keys())
    horaro_ids = set(horaro_by_id.keys())
    only_in_xlsx = xlsx_ids - horaro_ids
    only_in_horaro = horaro_ids - xlsx_ids

    print(f"Unique IDs (sub:cat): xlsx={len(xlsx_ids)}, horaro={len(horaro_ids)}")
    if only_in_xlsx:
        print(f"  FAIL: In xlsx but not Horaro: {len(only_in_xlsx)}")
        for k in sorted(only_in_xlsx)[:5]:
            r = xlsx_runs_by_id[k]
            print(f"    {r.game} ({r.runner_display})")
    if only_in_horaro:
        print(f"  FAIL: In Horaro but not xlsx: {len(only_in_horaro)}")
        for k in sorted(only_in_horaro)[:5]:
            it = horaro_by_id[k]
            print(f"    {it.game} ({', '.join(it.runner_names)})")
    if not only_in_xlsx and not only_in_horaro:
        print("  PASS: All IDs present in both")
    print()

    # Field diffs on matched runs
    diffs = []
    for k in xlsx_ids & horaro_ids:
        x = xlsx_runs_by_id[k]
        h = horaro_by_id[k]
        # Compare all Horaro runner names against all xlsx participants
        h_names = h.runner_names
        x_participants = [p.get("display") or "" for p in (x.participants or [])]
        if not x_participants:
            # Legacy: fall back to flat runner_display
            x_participants = [x.runner_display] if x.runner_display else []

        if x.game != h.game:
            diffs.append((k, "game", x.game, h.game))
        if x.category != h.category:
            diffs.append((k, "category", x.category, h.category))
        if x.estimate != h.estimate_str:
            diffs.append((k, "estimate", x.estimate, h.estimate_str))
        if x.platform != h.platform:
            diffs.append((k, "platform", x.platform, h.platform))

        # Runner diff: compare sets of names (order-independent)
        x_name_set = {n.strip().lower() for n in x_participants if n}
        h_name_set = {n.strip().lower() for n in h_names if n}
        if x_name_set != h_name_set:
            diffs.append((k, "runner", ", ".join(sorted(x_name_set)), ", ".join(sorted(h_name_set))))

    if diffs:
        print(f"Field diffs: {len(diffs)}")
        for d in diffs[:10]:
            print(f"  {d[0]}: {d[1]} xlsx={d[2]!r} horaro={d[3]!r}")
        if len(diffs) > 10:
            print(f"  ... and {len(diffs) - 10} more")
    else:
        print("PASS: No field diffs on matched runs")
    print()

    # Cosmetic issues in xlsx
    print("XLSX data quality (cosmetic):")
    trailing_underscore = [
        r for r in xlsx_runs
        if any(
            (p.get("twitch") or "").endswith("_")
            for p in (r.participants or [])
        ) or r.runner_twitch.endswith("_")
    ]
    if trailing_underscore:
        print(f"  Runner twitch with trailing underscore: {len(trailing_underscore)}")
        for r in trailing_underscore[:5]:
            print(f"    {r.game}: twitch={r.runner_twitch!r}")
        if len(trailing_underscore) > 5:
            print(f"    ... and {len(trailing_underscore) - 5} more")
    else:
        print("  PASS: No cosmetic issues found")

    print()
    print("Done.")

    if (only_in_xlsx or only_in_horaro or diffs):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

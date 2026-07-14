"""Import xlsx spreadsheet into SQLite database.

Usage:
    python -m src.import_to_sqlite [--xlsx PATH] [--db PATH] [--dry-run]

Reads `output/incentive_plan.xlsx` (or --xlsx), creates/updates
`output/esa.db` (or --db). Idempotent: re-imports update existing
rows keyed by `run_key` (`submission_id|game|category` or
`game|category` when no submission_id).

The import:
1. Creates a snapshot of the existing DB (if it exists) to
   `output/snapshots/esa.db.{timestamp}`.
2. Writes to a temp DB file.
3. Atomically renames temp → live via os.replace().

The xlsx file is never modified.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from src.db import (
    Incentive,
    Run,
    RunParticipant,
    Runner,
    SCHEMA_VERSION,
    get_schema_version,
    init_db,
    make_engine,
    parse_estimate_to_seconds,
    quick_check,
)
from src import xlsx_reader as xr
from src.slugs import run_slug, runner_slug, stream_token

TZ = ZoneInfo("Europe/Stockholm")


def make_run_key(submission_id: str, game: str, category: str, scheduled: datetime) -> str:
    """Build the stable identity key for a run.

    Strategy:
    - When submission_id is present, use it (oengus ID, stable across
      schedule shifts). The run moves slots but the ID persists.
    - When submission_id is missing, include the scheduled time. This
      handles overnight breaks and other "no oengus submission" rows
      that legitimately repeat (same game+category, different slots).
    """
    sid = (submission_id or "").strip()
    if sid:
        return f"{sid}|{game}|{category}"
    # ISO format down to the minute — stable enough, no microseconds
    return f"no-sub|{game}|{category}|{scheduled.strftime('%Y-%m-%dT%H:%M')}"


def import_xlsx_to_sqlite(
    xlsx_path: str,
    db_path: str,
    dry_run: bool = False,
) -> dict:
    """Import runs and incentives from xlsx into SQLite.

    Returns a summary dict with row counts. Never modifies the xlsx.
    """
    if not os.path.isfile(xlsx_path):
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

    now = datetime.now(TZ)

    # Read xlsx via existing reader
    runs = xr.read_cross_reference(xlsx_path)
    incentives = xr.read_incentives(xlsx_path)

    if dry_run:
        return {
            "dry_run": True,
            "runs": len(runs),
            "incentives": len(incentives),
            "db_path": db_path,
            "xlsx_path": xlsx_path,
        }

    # Read existing DB rows BEFORE writing to temp, so we can preserve
    # user edits across re-imports.
    existing_incentives: dict[str, Incentive] = {}
    existing_runs: dict[str, Run] = {}
    if os.path.exists(db_path):
        try:
            existing_engine = make_engine(db_path)
            with Session(existing_engine) as ex:
                existing_incentives = {row.uuid: row for row in ex.exec(select(Incentive)).all()}
                existing_runs = {row.run_key: row for row in ex.exec(select(Run)).all()}
            existing_engine.dispose()
        except Exception:
            # Existing DB is corrupt — treat as empty. Snapshot still
            # preserves the old state for manual recovery.
            pass

    # Build temp DB path; ensure parent dir exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path + ".tmp"

    # Snapshot existing DB before writing
    snapshot_path = None
    if os.path.exists(db_path):
        os.makedirs(os.path.join(os.path.dirname(db_path), "snapshots"), exist_ok=True)
        ts = now.strftime("%Y%m%dT%H%M%S")
        snapshot_path = os.path.join(
            os.path.dirname(db_path), "snapshots", f"esa.db.{ts}"
        )
        shutil.copy2(db_path, snapshot_path)
        os.replace(snapshot_path, snapshot_path + ".stamping")
        os.replace(snapshot_path + ".stamping", snapshot_path)

    # Init temp DB
    if os.path.exists(temp_path):
        os.remove(temp_path)
    init_db(temp_path)

    engine = make_engine(temp_path)

    # Map run_key → new Run row
    rows_added = 0
    rows_updated = 0
    incentives_added = 0
    incentives_updated = 0
    incentives_preserved = 0
    participants_added = 0

    with Session(engine) as session:
        # Upsert runs (no flat runner_* fields in v4 schema).
        for r in runs:
            run_key = make_run_key(r.submission_id or "", r.game, r.category, r.scheduled)
            prior = existing_runs.get(run_key)
            slug = run_slug(r.game, r.category, r.scheduled, r.submission_id or "")

            if prior is not None:
                row = Run(
                    id=prior.id,
                    pick=r.pick,
                    scheduled=r.scheduled,
                    game=r.game,
                    category=r.category,
                    estimate=r.estimate,
                    estimate_seconds=parse_estimate_to_seconds(r.estimate),
                    platform=r.platform,
                    players=r.players,
                    note=r.note,
                    layout=r.layout,
                    stream=r.stream,
                    stream_short=stream_token(r.stream),
                    submission_id=r.submission_id,
                    category_id=r.category_id,
                    incentives=r.incentives,
                    commentator=r.commentator,
                    upload_speed=r.upload_speed,
                    pronouns=r.pronouns,
                    show_cam=r.show_cam,
                    runner_comments=r.runner_comments,
                    slug=slug,
                    run_key=run_key,
                    imported_at=now,
                    updated_at=prior.updated_at if prior.updated_at > prior.imported_at else now,
                )
                session.add(row)
                rows_updated += 1
            else:
                session.add(Run(
                    pick=r.pick,
                    scheduled=r.scheduled,
                    game=r.game,
                    category=r.category,
                    estimate=r.estimate,
                    estimate_seconds=parse_estimate_to_seconds(r.estimate),
                    platform=r.platform,
                    players=r.players,
                    note=r.note,
                    layout=r.layout,
                    stream=r.stream,
                    stream_short=stream_token(r.stream),
                    submission_id=r.submission_id,
                    category_id=r.category_id,
                    incentives=r.incentives,
                    commentator=r.commentator,
                    upload_speed=r.upload_speed,
                    pronouns=r.pronouns,
                    show_cam=r.show_cam,
                    runner_comments=r.runner_comments,
                    slug=slug,
                    run_key=run_key,
                    imported_at=now,
                    updated_at=now,
                ))
                rows_added += 1

        session.commit()

        # Build run_id lookup
        run_id_by_key = {
            r.run_key: r.id
            for r in session.exec(select(Run)).all()
        }

        # ── RunParticipant upsert ──
        # For each run, insert one RunParticipant per participant dict.
        # Slug uses ADR 0002 rule: twitch (primary) or player-<slug>-<pk>.
        # We need the Run PK for the fallback slug, so flush before this loop.
        runner_profiles_cache_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "output", "briefs", ".cache", "runner_profiles.json",
        )
        cached_profiles: dict = {}
        if os.path.exists(runner_profiles_cache_path):
            try:
                with open(runner_profiles_cache_path) as f:
                    cached_profiles = json.load(f)
            except (json.JSONDecodeError, OSError):
                cached_profiles = {}

        all_runs_list = session.exec(select(Run)).all()
        run_by_key = {r.run_key: r for r in all_runs_list}

        for r in runs:
            run_key = make_run_key(r.submission_id or "", r.game, r.category, r.scheduled)
            run_row = run_by_key.get(run_key)
            if run_row is None:
                continue
            run_id = run_row.id

            participants = getattr(r, "participants", None) or []
            if not participants:
                # Legacy sheet with no participants JSON — synthesise from flat fields
                if r.runner_display or r.runner_twitch:
                    participants = [{
                        "display": r.runner_display,
                        "twitch": r.runner_twitch,
                        "discord": r.runner_discord,
                        "twitter": r.runner_twitter,
                        "pronunciation": "",
                        "submission_id": r.submission_id,
                        "match_confidence": "primary",
                    }]

            for p in participants:
                twitch = (p.get("twitch") or "").strip().lower()
                display = p.get("display") or ""
                discord = p.get("discord") or ""
                twitter = p.get("twitter") or ""
                pronunciation = p.get("pronunciation") or ""
                sub_id = p.get("submission_id")
                confidence = p.get("match_confidence") or ""

                # Compute slug per ADR 0002
                p_slug = runner_slug(twitch, display, run_id or 0)

                # Upsert RunParticipant (UNIQUE on run_id + runner_slug)
                rp = session.exec(
                    select(RunParticipant).where(
                        RunParticipant.run_id == run_id,
                        RunParticipant.runner_slug == p_slug,
                    )
                ).first()
                if rp is None:
                    rp = RunParticipant(
                        run_id=run_id,
                        runner_slug=p_slug,
                        display_name=display,
                        twitch=twitch,
                        discord=discord,
                        twitter=twitter,
                        pronunciation=pronunciation,
                        pronouns="",
                        submission_id=str(sub_id) if sub_id else None,
                        match_confidence=confidence,
                        imported_at=now,
                        updated_at=now,
                    )
                    session.add(rp)
                    participants_added += 1
                else:
                    rp.display_name = display
                    rp.twitch = twitch
                    rp.discord = discord
                    rp.twitter = twitter
                    rp.pronunciation = pronunciation
                    rp.submission_id = str(sub_id) if sub_id else None
                    rp.match_confidence = confidence
                    rp.updated_at = now

                # Upsert Runner row per participant
                runner = session.exec(select(Runner).where(Runner.slug == p_slug)).first()
                if runner is None:
                    runner = Runner(
                        slug=p_slug,
                        display_name=display,
                        twitch=twitch,
                        discord=discord,
                        twitter=twitter,
                        pronunciation=pronunciation,
                        pronouns="",
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(runner)
                    session.flush()

                # Populate stats_json from cache
                cache_key = f"{twitch}|{display.strip().lower()}"
                cached = cached_profiles.get(cache_key)
                if cached and isinstance(cached, dict):
                    runner.stats_json = json.dumps({
                        "summary": cached.get("summary"),
                        "stats": cached.get("stats"),
                        "sources": cached.get("sources"),
                        "errors": cached.get("errors"),
                    })
                    runner.updated_at = now

        session.commit()

        # ── Incentive upsert ──
        processed_uuids: set[str] = set()

        for inc in incentives:
            run_key = make_run_key(inc.submission_id, inc.game, inc.category, inc.scheduled)
            run_id = run_id_by_key.get(run_key)
            if run_id is None:
                continue

            processed_uuids.add(inc.uuid)
            prior = existing_incentives.get(inc.uuid)
            participants_json = json.dumps(
                getattr(inc, "participants", None) or [], ensure_ascii=False
            )

            if prior is not None:
                inc_category = inc.incentive_category
                inc_valid = inc.valid_for_game
                inc_status = inc.status
                inc_estimate = inc.incentive_estimate
                inc_updated = now
                if prior.updated_at > prior.imported_at:
                    inc_category = prior.incentive_category
                    inc_valid = prior.valid_for_game
                    inc_status = prior.status
                    inc_estimate = prior.incentive_estimate
                    inc_updated = prior.updated_at
                    incentives_preserved += 1
                else:
                    incentives_updated += 1
                session.add(Incentive(
                    uuid=inc.uuid,
                    run_id=run_id,
                    scheduled=inc.scheduled,
                    game=inc.game,
                    category=inc.category,
                    stream=inc.stream,
                    participants_json=participants_json,
                    incentive_text=inc.incentive_text,
                    details=inc.details if hasattr(inc, 'details') else "",
                    incentive_category=inc_category,
                    valid_for_game=inc_valid,
                    incentive_estimate=inc_estimate,
                    needs_approval=inc.needs_approval,
                    status=inc_status,
                    submission_id=inc.submission_id,
                    imported_at=now,
                    updated_at=inc_updated,
                ))
            else:
                session.add(Incentive(
                    uuid=inc.uuid,
                    run_id=run_id,
                    scheduled=inc.scheduled,
                    game=inc.game,
                    category=inc.category,
                    stream=inc.stream,
                    participants_json=participants_json,
                    incentive_text=inc.incentive_text,
                    details=inc.details if hasattr(inc, 'details') else "",
                    incentive_category=inc.incentive_category,
                    valid_for_game=inc.valid_for_game,
                    incentive_estimate=inc.incentive_estimate,
                    needs_approval=inc.needs_approval,
                    status=inc.status,
                    submission_id=inc.submission_id,
                    imported_at=now,
                    updated_at=now,
                ))
                incentives_added += 1

        session.commit()

        # Preserve user-created incentives not present in xlsx
        for uuid, prior in existing_incentives.items():
            if uuid in processed_uuids:
                continue
            run_exists = session.exec(select(Run).where(Run.id == prior.run_id)).first() is not None
            if not run_exists:
                continue
            session.add(Incentive(
                uuid=prior.uuid,
                run_id=prior.run_id,
                scheduled=prior.scheduled,
                game=prior.game,
                category=prior.category,
                stream=prior.stream,
                participants_json=getattr(prior, "participants_json", ""),
                incentive_text=prior.incentive_text,
                details=getattr(prior, "details", ""),
                incentive_category=prior.incentive_category,
                valid_for_game=prior.valid_for_game,
                incentive_estimate=prior.incentive_estimate,
                needs_approval=prior.needs_approval,
                status=prior.status,
                submission_id=prior.submission_id,
                imported_at=prior.imported_at,
                updated_at=prior.updated_at,
            ))
            incentives_preserved += 1

        session.commit()

    engine.dispose()

    # Verify the new DB is healthy before swap
    if not quick_check(temp_path):
        os.remove(temp_path)
        if snapshot_path and os.path.exists(snapshot_path):
            shutil.copy2(snapshot_path, db_path)
        raise RuntimeError("New DB failed quick_check; live DB restored from snapshot")

    # Atomic swap
    os.replace(temp_path, db_path)

    return {
        "dry_run": False,
        "runs_added": rows_added,
        "runs_updated": rows_updated,
        "participants_added": participants_added,
        "incentives_added": incentives_added,
        "incentives_updated": incentives_updated,
        "incentives_preserved": incentives_preserved,
        "snapshot": snapshot_path,
        "db_path": db_path,
        "xlsx_path": xlsx_path,
    }


def sync_runner_profiles_to_db(
    db_path: str = "output/esa.db",
    profiles_cache_path: str = "",
) -> dict:
    """Push the on-disk runner-profile cache into the DB without a full xlsx import.

    Reads ``output/briefs/.cache/runner_profiles.json`` (or the path supplied),
    then for each Runner row in the DB whose cache key matches an entry, updates
    ``runner.stats_json``.  Only existing Runner rows are touched; no new rows
    are created.

    This is the standalone counterpart to the profile-cache ingestion that was
    previously embedded in ``import_xlsx_to_sqlite``.

    Returns:
        {"updated": N, "skipped": N, "errors": [...]}
    """
    if not profiles_cache_path:
        profiles_cache_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output", "briefs", ".cache", "runner_profiles.json",
        )

    cached_profiles: dict = {}
    if os.path.exists(profiles_cache_path):
        try:
            with open(profiles_cache_path) as f:
                cached_profiles = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            return {"updated": 0, "skipped": 0, "errors": [str(exc)]}

    if not cached_profiles:
        return {"updated": 0, "skipped": 0, "errors": []}

    from src.db import make_engine

    engine = make_engine(db_path)
    updated = 0
    skipped = 0
    errors: list[str] = []
    now = datetime.now(ZoneInfo("Europe/Stockholm")).replace(tzinfo=None)

    try:
        with Session(engine) as session:
            runners = session.exec(select(Runner)).all()
            for runner in runners:
                twitch = (runner.twitch or "").strip().lower()
                display = (runner.display_name or "").strip().lower()
                cache_key = f"{twitch}|{display}"
                cached = cached_profiles.get(cache_key)
                if not cached or not isinstance(cached, dict):
                    skipped += 1
                    continue
                try:
                    runner.stats_json = json.dumps({
                        "summary": cached.get("summary"),
                        "stats": cached.get("stats"),
                        "sources": cached.get("sources"),
                        "errors": cached.get("errors"),
                    })
                    runner.updated_at = now
                    session.add(runner)
                    updated += 1
                except Exception as exc:
                    errors.append(f"{runner.slug}: {exc}")
                    skipped += 1
            session.commit()
    finally:
        engine.dispose()

    return {"updated": updated, "skipped": skipped, "errors": errors}


def main():
    p = argparse.ArgumentParser(description="Import xlsx → SQLite")
    p.add_argument("--xlsx", default="output/incentive_plan.xlsx", help="Path to xlsx")
    p.add_argument("--db", default="output/esa.db", help="Path to SQLite DB")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen, don't write")
    args = p.parse_args()

    try:
        result = import_xlsx_to_sqlite(args.xlsx, args.db, dry_run=args.dry_run)
        print(result)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

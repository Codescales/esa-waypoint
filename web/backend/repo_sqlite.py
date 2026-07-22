"""SQLite-backed implementation of the IncentiveRepo Protocol.

Reads runs + incentives from `output/esa.db` (or wherever DB_PATH
points). Phase 2.1 is read-only; writes come in 2.2 (admin) and 2.3
(incentive editing).
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .models import (
    IncentiveDTO, IncentivePatch, IncentiveCreateRequest,
    RunDTO, RunCreateRequest, StaleInfo, RunnerDTO, RunnerProfileDTO, RunnerPBDTO, RunnerPBEntry,
    JobDTO, JobAlreadyRunningError, ParticipantDTO, NewsItemDTO,
)
from src.db import Incentive, Run, RunParticipant, Runner, Job, NewsItem, make_engine
from src.slugs import runner_slug, run_slug as make_run_slug
from src.import_to_sqlite import make_run_key
from src import audit as audit_log

TZ = ZoneInfo("Europe/Stockholm")


class SqliteIncentiveRepo:
    def __init__(self, db_path: str, max_stale_hours: float = 6.0):
        self._db_path = db_path
        self._max_stale_hours = max_stale_hours

    def _engine(self):
        return make_engine(self._db_path)

    def streams(self) -> list[str]:
        seen: dict[str, int] = {}
        with Session(self._engine()) as s:
            for stream in s.exec(select(Run.stream).distinct()).all():
                if stream not in seen:
                    seen[stream] = len(seen)
        return sorted(seen, key=lambda k: seen[k])

    def _participants_for_run(self, run_id: int, session) -> list[ParticipantDTO]:
        """Load RunParticipant rows for a run and return as ParticipantDTO list."""
        rows = session.exec(
            select(RunParticipant).where(RunParticipant.run_id == run_id)
        ).all()
        return [
            ParticipantDTO(
                slug=rp.runner_slug,
                display_name=rp.display_name,
                twitch=rp.twitch,
                discord=rp.discord,
                twitter=rp.twitter,
                pronouns=rp.pronouns,
                pronunciation=rp.pronunciation,
                submission_id=rp.submission_id,
                match_confidence=rp.match_confidence,
            )
            for rp in rows
        ]

    def _run_to_dto(self, r: Run, session=None) -> RunDTO:
        scheduled = r.scheduled
        if scheduled.tzinfo is None:
            from zoneinfo import ZoneInfo
            scheduled = scheduled.replace(tzinfo=ZoneInfo("Europe/Stockholm"))

        participants: list[ParticipantDTO] = []
        if session is not None:
            participants = self._participants_for_run(r.id or 0, session)

        # Flat fields populated from first participant for transitional compat.
        p0 = participants[0] if participants else None
        runner_display = p0.display_name if p0 else ""
        runner_twitch = p0.twitch if p0 else ""
        runner_discord = p0.discord if p0 else ""
        runner_twitter = p0.twitter if p0 else ""
        r_slug = p0.slug if p0 else runner_slug(runner_twitch, runner_display, r.id or 0)

        return RunDTO(
            pick=r.pick,
            scheduled=scheduled,
            scheduled_date=scheduled.strftime("%Y-%m-%d"),
            game=r.game,
            category=r.category,
            estimate=r.estimate,
            estimate_seconds=r.estimate_seconds,
            platform=r.platform,
            players=r.players,
            runner_display=runner_display,
            runner_twitch=runner_twitch,
            runner_discord=runner_discord,
            runner_twitter=runner_twitter,
            runner_slug=r_slug,
            note=r.note,
            layout=r.layout,
            stream=r.stream,
            stream_short=r.stream_short,
            submission_id=r.submission_id,
            category_id=r.category_id,
            incentives=r.incentives,
            commentator=r.commentator,
            upload_speed=r.upload_speed,
            pronouns=r.pronouns,
            show_cam=r.show_cam,
            runner_comments=r.runner_comments,
            slug=r.slug,
            participants=participants,
        )

    def runs(
        self,
        *,
        stream: str = "",
        window: Optional[tuple[datetime, datetime]] = None,
        next_hours: float = 0,
        marathon: bool = False,
        search: str = "",
    ) -> list[RunDTO]:
        from zoneinfo import ZoneInfo
        TZ = ZoneInfo("Europe/Stockholm")

        with Session(self._engine()) as s:
            stmt = select(Run)
            rows = s.exec(stmt).all()

            def _aware(dt: datetime) -> datetime:
                return dt if dt.tzinfo else dt.replace(tzinfo=TZ)

            if search:
                q = search.lower()
                rows = [
                    r for r in rows
                    if q in r.game.lower()
                    or q in r.category.lower()
                    or any(
                        q in (rp.display_name or "").lower()
                        for rp in self._participants_for_run(r.id or 0, s)
                    )
                ]
            if stream:
                stream_lower = stream.lower()
                rows = [r for r in rows if r.stream.lower() == stream_lower or r.stream_short.lower() == stream_lower]

            if window:
                start, end = window
                if start.tzinfo is None:
                    start = start.replace(tzinfo=TZ)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=TZ)
                rows = [r for r in rows if start <= _aware(r.scheduled) < end]
            elif next_hours > 0:
                now = datetime.now(TZ)
                rows = [r for r in rows if now <= _aware(r.scheduled) < now + timedelta(hours=next_hours)]
            elif not marathon:
                now = datetime.now(TZ)
                rows = [r for r in rows if not _aware(r.scheduled) < now - timedelta(hours=2)]
                rows.sort(key=lambda r: r.scheduled)
                rows = rows[:50]

            return [self._run_to_dto(r, s) for r in rows]

    def run(self, slug: str) -> Optional[RunDTO]:
        with Session(self._engine()) as s:
            r = s.exec(select(Run).where(Run.slug == slug)).first()
            if r is None:
                return None
            return self._run_to_dto(r, s)

    def _incentive_to_dto(self, inc: Incentive, run: Run) -> IncentiveDTO:
        scheduled = inc.scheduled
        if scheduled.tzinfo is None:
            from zoneinfo import ZoneInfo
            scheduled = scheduled.replace(tzinfo=ZoneInfo("Europe/Stockholm"))

        # Parse participants from JSON blob.
        # Two formats exist in the wild:
        #   - import format: {"display": ..., "twitch": ..., "discord": ..., "twitter": ...}
        #   - DTO format (written by create_incentive before this fix):
        #     {"slug": ..., "display_name": ..., "twitch": ..., ...}
        # Handle both so existing rows are not broken.
        participants: list[ParticipantDTO] = []
        if inc.participants_json:
            try:
                raw = json.loads(inc.participants_json)
                if isinstance(raw, list):
                    participants = [
                        ParticipantDTO(
                            slug=(
                                p.get("slug", "")
                                or p.get("twitch", "").strip().lower()
                                or p.get("display", "")
                                or p.get("display_name", "")
                            ),
                            display_name=p.get("display_name", "") or p.get("display", ""),
                            twitch=p.get("twitch", ""),
                            discord=p.get("discord", ""),
                            twitter=p.get("twitter", ""),
                            pronouns=p.get("pronouns", ""),
                            pronunciation=p.get("pronunciation", ""),
                            submission_id=p.get("submission_id"),
                            match_confidence=p.get("match_confidence", ""),
                        )
                        for p in raw
                    ]
            except (json.JSONDecodeError, TypeError):
                pass

        p0 = participants[0] if participants else None
        runner_display = p0.display_name if p0 else ""
        runner_twitch = p0.twitch if p0 else ""
        runner_discord = p0.discord if p0 else ""
        r_slug = p0.slug if p0 else runner_slug(runner_twitch, runner_display, run.id or 0)

        return IncentiveDTO(
            scheduled=scheduled,
            scheduled_date=scheduled.strftime("%Y-%m-%d"),
            game=inc.game,
            category=inc.category,
            stream=inc.stream,
            runner_display=runner_display,
            runner_twitch=runner_twitch,
            runner_discord=runner_discord,
            runner_slug=r_slug,
            incentive_text=inc.incentive_text,
            details=inc.details,
            incentive_category=inc.incentive_category,
            valid_for_game=inc.valid_for_game,
            incentive_estimate=inc.incentive_estimate,
            needs_approval=inc.needs_approval,
            status=inc.status,
            submission_id=inc.submission_id,
            uuid=inc.uuid,
            run_slug=run.slug,
            participants=participants,
        )

    def incentives(
        self,
        *,
        run_slug: str = "",
        status: str = "",
        category: str = "",
        stream: str = "",
        upcoming: bool = False,
    ) -> list[IncentiveDTO]:
        with Session(self._engine()) as s:
            stmt = select(Incentive, Run).join(Run, Run.id == Incentive.run_id)
            incs = s.exec(stmt).all()

        now = datetime.now(TZ)
        result: list[IncentiveDTO] = []
        for inc, run in incs:
            if run_slug and run.slug != run_slug:
                continue
            if status and (inc.status or "").lower() != status.lower():
                continue
            if category and (inc.incentive_category or "").lower() != category.lower():
                continue
            if stream:
                stream_lower = stream.lower()
                if (inc.stream or "").lower() != stream_lower and (run.stream_short or "").lower() != stream_lower:
                    continue
            if upcoming:
                scheduled = inc.scheduled
                if scheduled.tzinfo is None:
                    scheduled = scheduled.replace(tzinfo=TZ)
                if scheduled < now:
                    continue
            result.append(self._incentive_to_dto(inc, run))

        return result

    def incentive(self, uuid: str) -> Optional[IncentiveDTO]:
        with Session(self._engine()) as s:
            row = s.exec(
                select(Incentive, Run).join(Run, Run.id == Incentive.run_id)
                .where(Incentive.uuid == uuid)
            ).first()
            if not row:
                return None
            inc, run = row
            return self._incentive_to_dto(inc, run)

    def patch_incentive(self, uuid: str, patch) -> Optional[IncentiveDTO]:
        """Update an incentive's editable fields. Sets updated_at to mark
        the row as user-edited (so re-imports preserve the change).
        Returns the updated DTO, or None if the uuid doesn't exist.
        """
        with Session(self._engine()) as s:
            row = s.get(Incentive, uuid)
            if row is None:
                return None
            run = s.get(Run, row.run_id)
            if run is None:
                return None

            data = patch.model_dump(exclude_unset=True) if hasattr(patch, "model_dump") else patch.dict(exclude_unset=True)
            for field, value in data.items():
                if value is not None:
                    setattr(row, field, value)
            row.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(row)
            s.commit()
            s.refresh(row)
            return self._incentive_to_dto(row, run)

    def create_incentive(self, body: IncentiveCreateRequest) -> IncentiveDTO:
        """Create a new incentive for a run. Generates uuid, fills
        run-derived fields from the joined Run row, sets imported_at
        and updated_at so re-import preserves the user-authored row.
        Raises HTTPException 404 if the run slug doesn't exist.
        """
        with Session(self._engine()) as s:
            run = s.exec(select(Run).where(Run.slug == body.run_slug)).first()
            if run is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Run not found")

            # Snapshot current participants for the incentive.
            # Use the raw import format (display/twitch keys) so _incentive_to_dto
            # can parse them the same way as xlsx-imported rows.
            participants = self._participants_for_run(run.id or 0, s)
            participants_json = json.dumps(
                [
                    {
                        "display": p.display_name,
                        "twitch": p.twitch,
                        "discord": p.discord,
                        "twitter": p.twitter,
                        "pronouns": p.pronouns,
                        "pronunciation": p.pronunciation,
                        "submission_id": p.submission_id,
                        "match_confidence": p.match_confidence,
                    }
                    for p in participants
                ],
                ensure_ascii=False,
            )

            now = datetime.now(TZ).replace(tzinfo=None)
            inc = Incentive(
                uuid=str(uuid4()),
                run_id=run.id,
                scheduled=run.scheduled,
                game=run.game,
                category=run.category,
                stream=run.stream,
                participants_json=participants_json,
                incentive_text=body.incentive_text,
                details=body.details if hasattr(body, 'details') else "",
                incentive_category=body.incentive_category,
                valid_for_game=body.valid_for_game,
                incentive_estimate=body.incentive_estimate,
                needs_approval="",
                status=body.status,
                submission_id="",
                imported_at=now,
                updated_at=now,
            )
            s.add(inc)
            s.commit()
            s.refresh(inc)
            return self._incentive_to_dto(inc, run)

    def delete_incentive(self, uuid: str) -> Optional[IncentiveDTO]:
        """Soft-delete an incentive by setting status='Removed'."""
        with Session(self._engine()) as s:
            row = s.get(Incentive, uuid)
            if row is None:
                return None
            run = s.get(Run, row.run_id)
            if run is None:
                return None
            row.status = "Removed"
            row.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(row)
            s.commit()
            s.refresh(row)
            return self._incentive_to_dto(row, run)

    def runner(self, slug: str) -> Optional[RunnerDTO]:
        """Look up a runner by slug, creating on demand from RunParticipant data if needed."""
        with Session(self._engine()) as s:
            runner = s.exec(select(Runner).where(Runner.slug == slug)).first()
            if runner is not None:
                return self._runner_to_dto(runner, s)

            # Find a RunParticipant whose runner_slug matches the requested slug
            rp = s.exec(
                select(RunParticipant).where(RunParticipant.runner_slug == slug)
            ).first()

            if rp is None:
                return None

            now = datetime.now(TZ).replace(tzinfo=None)
            placeholder = f"tmp-{uuid4()}"
            runner = Runner(
                slug=placeholder,
                display_name=rp.display_name,
                twitch=rp.twitch,
                discord=rp.discord,
                twitter=rp.twitter,
                pronouns=rp.pronouns,
                created_at=now,
                updated_at=now,
            )
            s.add(runner)
            s.commit()
            s.refresh(runner)

            final_slug = runner_slug(rp.twitch, rp.display_name, runner.id or 0)
            runner.slug = final_slug
            s.add(runner)
            s.commit()
            s.refresh(runner)
            return self._runner_to_dto(runner, s)

    def runners(self) -> list[RunnerDTO]:
        """Return all runners ordered by display_name."""
        with Session(self._engine()) as s:
            all_runners = s.exec(select(Runner).order_by(Runner.display_name)).all()
            return [self._runner_to_dto(r, s) for r in all_runners]

    def _runner_to_dto(self, runner: Runner, session) -> RunnerDTO:
        # Find all runs this runner participates in via RunParticipant
        rps = session.exec(
            select(RunParticipant).where(RunParticipant.runner_slug == runner.slug)
        ).all()
        run_ids = [rp.run_id for rp in rps]
        matched_runs = []
        if run_ids:
            for r in session.exec(select(Run).where(Run.id.in_(run_ids))).all():
                matched_runs.append(r)

        upcoming = [
            self._run_to_dto(r, session)
            for r in sorted(matched_runs, key=lambda x: x.scheduled)
            if r.scheduled >= datetime.now(TZ).replace(tzinfo=None)
        ][:5]

        esa_events = set()
        for r in matched_runs:
            event = r.stream.split(" (Stream")[0] if r.stream else ""
            if event:
                esa_events.add(event)

        return RunnerDTO(
            slug=runner.slug,
            display_name=runner.display_name,
            twitch=runner.twitch,
            discord=runner.discord,
            twitter=runner.twitter,
            pronouns=runner.pronouns,
            pronunciation=runner.pronunciation,
            run_count=len(matched_runs),
            esa_count=len(esa_events),
            first_esa=min(r.scheduled for r in matched_runs).strftime("%Y-%m-%d") if matched_runs else None,
            upcoming_runs=upcoming,
        )

    def runner_profile(self, slug: str) -> Optional[RunnerProfileDTO]:
        """Return the composite runner profile from the DB.

        Reads `Runner.stats_json` (populated during import from the
        cached runner-profile JSON). If the column is empty, returns
        a minimal DTO with `has_profile=False` so the caller can
        trigger a refresh.
        """
        with Session(self._engine()) as s:
            runner = s.exec(select(Runner).where(Runner.slug == slug)).first()
            if runner is None:
                return None

            stats: dict = {}
            if runner.stats_json:
                try:
                    stats = json.loads(runner.stats_json)
                except (json.JSONDecodeError, TypeError):
                    stats = {}

            return RunnerProfileDTO(
                slug=runner.slug,
                display_name=runner.display_name,
                twitch=runner.twitch,
                discord=runner.discord,
                twitter=runner.twitter,
                pronouns=runner.pronouns,
                pronunciation=runner.pronunciation,
                summary=stats.get("summary"),
                stats=stats.get("stats"),
                sources=stats.get("sources", []),
                errors=stats.get("errors", []),
                has_profile=bool(runner.stats_json),
            )

    def runner_pbs(self, slug: str) -> Optional[RunnerPBDTO]:
        with Session(self._engine()) as s:
            runner = s.exec(select(Runner).where(Runner.slug == slug)).first()
            if runner is None:
                return None

            raw = runner.pbs_json or "[]"
            try:
                entries = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                entries = []

            pbs = [RunnerPBEntry(**e) for e in entries if isinstance(e, dict)]

            return RunnerPBDTO(
                slug=runner.slug,
                display_name=runner.display_name,
                pbs=pbs,
                has_pbs=bool(pbs),
            )

    def runner_runs(self, slug: str, limit: int = 5) -> list[RunDTO]:
        with Session(self._engine()) as s:
            rps = s.exec(
                select(RunParticipant).where(RunParticipant.runner_slug == slug)
            ).all()
            run_ids = [rp.run_id for rp in rps]
            matched: list[Run] = []
            if run_ids:
                for r in s.exec(select(Run).where(Run.id.in_(run_ids))).all():
                    matched.append(r)

            matched.sort(key=lambda r: r.scheduled)
            now = datetime.now(TZ)
            upcoming = [r for r in matched if r.scheduled >= now.replace(tzinfo=None)]
            return [self._run_to_dto(r, s) for r in upcoming[:limit]]

    def spreadsheet_age(self) -> StaleInfo:
        from src.db import get_schema_version
        if not os.path.exists(self._db_path):
            return StaleInfo(age_hours=None, is_stale=True, is_missing=True)

        schema_version = get_schema_version(self._db_path)
        if schema_version == 0:
            return StaleInfo(age_hours=None, is_stale=True, is_missing=False)

        mtime = datetime.fromtimestamp(os.path.getmtime(self._db_path), tz=__import__("datetime").timezone.utc)
        now = datetime.now(__import__("datetime").timezone.utc)
        age = (now - mtime).total_seconds() / 3600
        return StaleInfo(
            age_hours=round(age, 1),
            is_stale=age > self._max_stale_hours,
            is_missing=False,
        )

    # ── Jobs ──

    def _job_to_dto(self, job: Job) -> JobDTO:
        return JobDTO(
            id=job.id,
            kind=job.kind,
            status=job.status,
            target=job.target,
            summary_json=job.summary_json,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )

    def create_job(self, kind: str, target: str = "") -> JobDTO:
        now = datetime.now(TZ).replace(tzinfo=None)
        job = Job(
            id=uuid4().hex,
            kind=kind,
            status="pending",
            target=target,
            summary_json="[]",
            error="",
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        engine = self._engine()
        try:
            with Session(engine) as s:
                s.add(job)
                s.commit()
                s.refresh(job)
                return self._job_to_dto(job)
        except IntegrityError:
            # Partial unique index violation: a pending/running job of this kind already exists
            with Session(engine) as s:
                existing = s.exec(
                    select(Job).where(Job.kind == kind, Job.status.in_(["pending", "running"]))
                ).first()
                if existing is not None:
                    raise JobAlreadyRunningError(existing.id)
                raise
        finally:
            engine.dispose()

    def get_job(self, id: str) -> Optional[JobDTO]:
        with Session(self._engine()) as s:
            job = s.get(Job, id)
            if job is None:
                return None
            return self._job_to_dto(job)

    def list_jobs(self, kind: str = "", status: str = "", limit: int = 50) -> list[JobDTO]:
        with Session(self._engine()) as s:
            stmt = select(Job)
            if kind:
                stmt = stmt.where(Job.kind == kind)
            if status:
                stmt = stmt.where(Job.status == status)
            stmt = stmt.order_by(Job.created_at.desc()).limit(limit)
            rows = s.exec(stmt).all()
        return [self._job_to_dto(r) for r in rows]

    def update_job(self, id: str, status: str = "", summary_json: str = "", error: str = "", completed_at: Optional[datetime] = None) -> Optional[JobDTO]:
        with Session(self._engine()) as s:
            job = s.get(Job, id)
            if job is None:
                return None
            if status:
                job.status = status
            if summary_json:
                job.summary_json = summary_json
            if error:
                job.error = error
            if completed_at is not None:
                job.completed_at = completed_at
            job.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(job)
            s.commit()
            s.refresh(job)
            return self._job_to_dto(job)

    def update_runner(self, slug: str, patch: dict) -> Optional[RunnerDTO]:
        with Session(self._engine()) as s:
            runner = s.exec(select(Runner).where(Runner.slug == slug)).first()
            if runner is None:
                return None
            for field, value in patch.items():
                if value is not None and hasattr(runner, field):
                    setattr(runner, field, value)
            runner.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(runner)
            s.commit()
            s.refresh(runner)
            return self._runner_to_dto(runner, s)

    def update_run(self, slug: str, patch: dict) -> Optional[RunDTO]:
        with Session(self._engine()) as s:
            run = s.exec(select(Run).where(Run.slug == slug)).first()
            if run is None:
                return None

            runner_slugs = patch.pop("runner_slugs", None)
            if runner_slugs is not None:
                now = datetime.now(TZ).replace(tzinfo=None)
                existing = s.exec(
                    select(RunParticipant).where(RunParticipant.run_id == run.id)
                ).all()
                for rp in existing:
                    s.delete(rp)
                for i, r_slug in enumerate(runner_slugs):
                    runner = s.exec(
                        select(Runner).where(Runner.slug == r_slug)
                    ).first()
                    rp = RunParticipant(
                        run_id=run.id,
                        runner_slug=r_slug,
                        display_name=runner.display_name if runner else r_slug,
                        twitch=runner.twitch if runner else "",
                        discord=runner.discord if runner else "",
                        twitter=runner.twitter if runner else "",
                        pronouns=runner.pronouns if runner else "",
                        pronunciation=runner.pronunciation if runner else "",
                        imported_at=now,
                        updated_at=now,
                    )
                    s.add(rp)

            for field, value in patch.items():
                if value is not None and hasattr(run, field):
                    setattr(run, field, value)
            run.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(run)
            s.commit()
            s.refresh(run)
            return self._run_to_dto(run, s)

    def create_run(self, body: RunCreateRequest) -> RunDTO:
        """Manually create a run (admin-only).

        Derives `slug` (ADR 0002 rule) and `run_key` (see
        src.import_to_sqlite.make_run_key) server-side. Raises
        HTTPException 409 if a run with the same run_key already
        exists (mirrors the xlsx import's upsert identity).
        """
        from fastapi import HTTPException

        scheduled = body.scheduled
        if scheduled.tzinfo is not None:
            scheduled = scheduled.astimezone(TZ).replace(tzinfo=None)

        run_key = make_run_key(body.submission_id or "", body.game, body.category, scheduled)
        slug = make_run_slug(body.game, body.category, scheduled.replace(tzinfo=TZ), body.submission_id or "")

        with Session(self._engine()) as s:
            existing = s.exec(select(Run).where(Run.run_key == run_key)).first()
            if existing is not None:
                raise HTTPException(status_code=409, detail="A run with this identity already exists")

            now = datetime.now(TZ).replace(tzinfo=None)
            run = Run(
                pick=body.pick,
                scheduled=scheduled,
                game=body.game,
                category=body.category,
                estimate=body.estimate,
                estimate_seconds=0,
                platform=body.platform,
                players=body.players,
                note=body.note,
                layout=body.layout,
                stream=body.stream,
                stream_short=body.stream_short,
                submission_id=body.submission_id,
                category_id=body.category_id,
                incentives=body.incentives,
                commentator=body.commentator,
                upload_speed=body.upload_speed,
                pronouns=body.pronouns,
                show_cam=body.show_cam,
                runner_comments=body.runner_comments,
                slug=slug,
                run_key=run_key,
                imported_at=now,
                updated_at=now,
            )
            s.add(run)
            s.commit()
            s.refresh(run)

            for r_slug in body.runner_slugs:
                runner = s.exec(select(Runner).where(Runner.slug == r_slug)).first()
                rp = RunParticipant(
                    run_id=run.id,
                    runner_slug=r_slug,
                    display_name=runner.display_name if runner else r_slug,
                    twitch=runner.twitch if runner else "",
                    discord=runner.discord if runner else "",
                    twitter=runner.twitter if runner else "",
                    pronouns=runner.pronouns if runner else "",
                    pronunciation=runner.pronunciation if runner else "",
                    imported_at=now,
                    updated_at=now,
                )
                s.add(rp)
            if body.runner_slugs:
                s.commit()
                s.refresh(run)

            return self._run_to_dto(run, s)

    def delete_run(self, slug: str) -> Optional[RunDTO]:
        """Hard-delete a run and its participant rows (admin-only).

        Refuses to delete (409) if the run still has incentives or
        host notes attached, so historical incentive/note data is
        never silently orphaned.
        """
        from fastapi import HTTPException
        from src.db import Note

        with Session(self._engine()) as s:
            run = s.exec(select(Run).where(Run.slug == slug)).first()
            if run is None:
                return None

            has_incentives = s.exec(select(Incentive).where(Incentive.run_id == run.id)).first()
            if has_incentives is not None:
                raise HTTPException(status_code=409, detail="Cannot delete a run with incentives; remove them first")
            has_notes = s.exec(select(Note).where(Note.run_id == run.id)).first()
            if has_notes is not None:
                raise HTTPException(status_code=409, detail="Cannot delete a run with notes; remove them first")

            dto = self._run_to_dto(run, s)

            participants = s.exec(select(RunParticipant).where(RunParticipant.run_id == run.id)).all()
            for rp in participants:
                s.delete(rp)
            s.delete(run)
            s.commit()
            return dto

    def cancel_job(self, id: str) -> Optional[JobDTO]:
        with Session(self._engine()) as s:
            job = s.get(Job, id)
            if job is None:
                return None
            if job.status not in ("pending", "running"):
                return self._job_to_dto(job)
            job.status = "failed"
            job.error = "cancelled by admin"
            job.completed_at = datetime.now(TZ).replace(tzinfo=None)
            job.updated_at = job.completed_at
            s.add(job)
            s.commit()
            s.refresh(job)
            return self._job_to_dto(job)

    # ------------------------------------------------------------------
    # News ticker
    # ------------------------------------------------------------------

    def _news_to_dto(self, item: NewsItem) -> NewsItemDTO:
        return NewsItemDTO(
            id=item.id or 0,
            source=item.source,
            category=item.category,
            source_label=item.source_label,
            title=item.title,
            url=item.url,
            summary=item.summary,
            published_at=item.published_at,
            fetched_at=item.fetched_at,
        )

    def schedule_game_names(self) -> list[str]:
        """Distinct game names in the schedule (for speedrun news lookup)."""
        with Session(self._engine()) as s:
            rows = s.exec(select(Run.game).distinct()).all()
        return sorted({(g or "").strip() for g in rows if (g or "").strip()})

    def list_news(self, limit: int = 50) -> list[NewsItemDTO]:
        """Return news items ordered by recency (published, then fetched)."""
        with Session(self._engine()) as s:
            rows = s.exec(select(NewsItem)).all()
        rows.sort(
            key=lambda n: (
                n.published_at or n.fetched_at,
                n.fetched_at,
            ),
            reverse=True,
        )
        return [self._news_to_dto(n) for n in rows[:limit]]

    def upsert_news_items(self, items: list[dict]) -> int:
        """Insert news items, skipping any whose dedupe_key already exists.

        Returns the number of newly inserted rows. Idempotent across refreshes.
        """
        now = datetime.now(TZ).replace(tzinfo=None)
        inserted = 0
        with Session(self._engine()) as s:
            existing_keys = set(
                s.exec(select(NewsItem.dedupe_key)).all()
            )
            for it in items:
                key = it.get("dedupe_key")
                if not key or key in existing_keys:
                    continue
                published = it.get("published_at")
                if isinstance(published, datetime) and published.tzinfo is not None:
                    published = published.astimezone(TZ).replace(tzinfo=None)
                s.add(NewsItem(
                    source=it.get("source", ""),
                    category=it.get("category", ""),
                    source_label=it.get("source_label", ""),
                    title=it.get("title", ""),
                    url=it.get("url", ""),
                    summary=it.get("summary", ""),
                    published_at=published,
                    fetched_at=now,
                    dedupe_key=key,
                ))
                existing_keys.add(key)
                inserted += 1
            s.commit()
        return inserted

    def prune_news(self, keep: int = 100) -> int:
        """Keep the newest `keep` items, delete the rest. Returns deleted count."""
        with Session(self._engine()) as s:
            rows = s.exec(select(NewsItem)).all()
            rows.sort(
                key=lambda n: (n.published_at or n.fetched_at, n.fetched_at),
                reverse=True,
            )
            to_delete = rows[keep:]
            for n in to_delete:
                s.delete(n)
            s.commit()
        return len(to_delete)

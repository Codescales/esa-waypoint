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
    RunDTO, StaleInfo, RunnerDTO, RunnerProfileDTO, RunnerPBDTO, RunnerPBEntry,
    JobDTO, JobAlreadyRunningError, ParticipantDTO,
)
from src.db import Incentive, Run, RunParticipant, Runner, Job, make_engine
from src.slugs import runner_slug
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
                    or q in (r.runner_display or "").lower()
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

        # Parse participants from JSON blob
        participants: list[ParticipantDTO] = []
        if inc.participants_json:
            try:
                raw = json.loads(inc.participants_json)
                if isinstance(raw, list):
                    participants = [
                        ParticipantDTO(
                            slug=p.get("twitch", "").strip().lower() or p.get("display", ""),
                            display_name=p.get("display", ""),
                            twitch=p.get("twitch", ""),
                            discord=p.get("discord", ""),
                            twitter=p.get("twitter", ""),
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
            game=inc.game,
            category=inc.category,
            stream=inc.stream,
            runner_display=runner_display,
            runner_twitch=runner_twitch,
            runner_discord=runner_discord,
            runner_slug=r_slug,
            incentive_text=inc.incentive_text,
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

            # Snapshot current participants for the incentive
            participants = self._participants_for_run(run.id or 0, s)
            participants_json = json.dumps(
                [p.model_dump() for p in participants], ensure_ascii=False
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
            for field, value in patch.items():
                if value is not None and hasattr(run, field):
                    setattr(run, field, value)
            run.updated_at = datetime.now(TZ).replace(tzinfo=None)
            s.add(run)
            s.commit()
            s.refresh(run)
            return self._run_to_dto(run, s)

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

"""Repository seam for incentive data access."""

from datetime import datetime
from typing import Optional, Protocol

from .models import RunDTO, IncentiveDTO, IncentivePatch, IncentiveCreateRequest, StaleInfo, RunnerDTO, JobDTO, RunnerProfileDTO, RunnerPBDTO, ParticipantDTO
from src.slugs import runner_slug
from src.db import parse_estimate_to_seconds


def _participants_from_run_row(r) -> list[ParticipantDTO]:
    """Build ParticipantDTO list from a RunRow's participants field."""
    dtos = []
    for p in (r.participants or []):
        twitch = (p.get("twitch") or "").strip().lower()
        display = p.get("display") or ""
        dtos.append(ParticipantDTO(
            slug=runner_slug(twitch, display, 0),
            display_name=display,
            twitch=twitch,
            discord=p.get("discord") or "",
            twitter=p.get("twitter") or "",
            submission_id=p.get("submission_id"),
            match_confidence=p.get("match_confidence") or "",
        ))
    return dtos


def _run_row_to_dto(r, stream_short: str, slug: str) -> RunDTO:
    """Convert an xlsx RunRow to RunDTO with participants."""
    participants = _participants_from_run_row(r)
    p0 = participants[0] if participants else None
    return RunDTO(
        pick=r.pick,
        scheduled=r.scheduled,
        game=r.game,
        category=r.category,
        estimate=r.estimate,
        estimate_seconds=parse_estimate_to_seconds(r.estimate),
        platform=r.platform,
        players=r.players,
        runner_display=p0.display_name if p0 else r.runner_display,
        runner_twitch=p0.twitch if p0 else r.runner_twitch,
        runner_discord=p0.discord if p0 else r.runner_discord,
        runner_twitter=p0.twitter if p0 else r.runner_twitter,
        runner_slug=p0.slug if p0 else runner_slug(r.runner_twitch, r.runner_display, 0),
        note=r.note,
        layout=r.layout,
        stream=r.stream,
        stream_short=stream_short,
        submission_id=r.submission_id,
        category_id=r.category_id,
        incentives=r.incentives,
        commentator=r.commentator,
        upload_speed=r.upload_speed,
        pronouns=r.pronouns,
        show_cam=r.show_cam,
        runner_comments=r.runner_comments,
        slug=slug,
        participants=participants,
    )


class IncentiveRepo(Protocol):
    def streams(self) -> list[str]: ...

    def runs(
        self,
        *,
        stream: str = "",
        window: Optional[tuple[datetime, datetime]] = None,
        next_hours: float = 0,
        marathon: bool = False,
    ) -> list[RunDTO]: ...

    def run(self, slug: str) -> Optional[RunDTO]: ...

    def incentives(
        self,
        *,
        run_slug: str = "",
        status: str = "",
        category: str = "",
        stream: str = "",
    ) -> list[IncentiveDTO]: ...

    def incentive(self, uuid: str) -> Optional[IncentiveDTO]: ...

    def patch_incentive(self, uuid: str, patch: IncentivePatch) -> Optional[IncentiveDTO]: ...

    def create_incentive(self, body: IncentiveCreateRequest) -> IncentiveDTO: ...

    def delete_incentive(self, uuid: str) -> Optional[IncentiveDTO]: ...

    def runner(self, slug: str) -> Optional[RunnerDTO]: ...

    def runner_profile(self, slug: str) -> Optional[RunnerProfileDTO]: ...

    def runner_pbs(self, slug: str) -> Optional[RunnerPBDTO]: ...

    def runner_runs(self, slug: str, limit: int = 5) -> list[RunDTO]: ...

    def spreadsheet_age(self) -> StaleInfo: ...

    def create_job(self, kind: str, target: str = "") -> JobDTO: ...

    def get_job(self, id: str) -> Optional[JobDTO]: ...

    def list_jobs(self, kind: str = "", status: str = "", limit: int = 50) -> list[JobDTO]: ...

    def update_job(self, id: str, status: str = "", summary_json: str = "", error: str = "", completed_at: Optional[datetime] = None) -> Optional[JobDTO]: ...

    def cancel_job(self, id: str) -> Optional[JobDTO]: ...

    def update_runner(self, slug: str, patch: dict) -> Optional[RunnerDTO]: ...

    def update_run(self, slug: str, patch: dict) -> Optional[RunDTO]: ...


class XlsxIncentiveRepo:
    """Reads schedule + incentives from the XLSX spreadsheet.

    Wraps src.xlsx_reader to produce typed DTOs.
    """

    def __init__(self, path: str, max_stale_hours: float = 6.0):
        self._path = path
        self._max_stale_hours = max_stale_hours

    def streams(self) -> list[str]:
        from src.xlsx_reader import get_distinct_streams
        return get_distinct_streams(self._path)

    def runs(
        self,
        *,
        stream: str = "",
        window: Optional[tuple[datetime, datetime]] = None,
        next_hours: float = 0,
        marathon: bool = False,
    ) -> list[RunDTO]:
        from src import xlsx_reader as xr
        from src.slugs import run_slug

        rows = xr.read_cross_reference(self._path)

        if stream:
            rows = xr.filter_runs_by_stream(rows, stream)
        if window:
            rows = xr.filter_runs_by_window(rows, window[0], window[1])
        elif next_hours > 0:
            now = datetime.now(xr.TZ)
            rows = xr.filter_runs_by_window(rows, now, now + __import__("datetime").timedelta(hours=next_hours))
        elif not marathon:
            now = datetime.now(xr.TZ)
            rows = [r for r in rows if not r.scheduled < now - __import__("datetime").timedelta(hours=2)]
            rows.sort(key=lambda r: r.scheduled)
            rows = rows[:50]

        return [
            _run_row_to_dto(
                r,
                stream_short=xr.stream_token_to_short(r.stream),
                slug=run_slug(r.game, r.category, r.scheduled, r.submission_id or ""),
            )
            for r in rows
        ]

    def run(self, slug: str) -> Optional[RunDTO]:
        for r in self.runs(marathon=True):
            if r.slug == slug:
                return r
        return None

    def incentives(
        self,
        *,
        run_slug: str = "",
        status: str = "",
        category: str = "",
        stream: str = "",
    ) -> list[IncentiveDTO]:
        from src import xlsx_reader as xr
        from src.slugs import run_slug as make_slug

        rows = xr.read_incentives(self._path)
        result: list[IncentiveDTO] = []

        for r in rows:
            slug = make_slug(r.game, r.category, r.scheduled, r.submission_id)
            if run_slug and slug != run_slug:
                continue
            if status and r.status.lower() != status.lower():
                continue
            if category and r.incentive_category.lower() != category.lower():
                continue
            if stream and xr.stream_token_to_short(r.stream).lower() != stream.lower() and r.stream.lower() != stream.lower():
                continue
            participants = [
                ParticipantDTO(
                    slug=runner_slug((p.get("twitch") or "").strip().lower(), p.get("display") or "", 0),
                    display_name=p.get("display") or "",
                    twitch=(p.get("twitch") or "").strip().lower(),
                    discord=p.get("discord") or "",
                    twitter=p.get("twitter") or "",
                    submission_id=p.get("submission_id"),
                    match_confidence=p.get("match_confidence") or "",
                )
                for p in (r.participants or [])
            ]
            p0 = participants[0] if participants else None
            result.append(IncentiveDTO(
                scheduled=r.scheduled,
                game=r.game,
                category=r.category,
                stream=r.stream,
                runner_display=p0.display_name if p0 else r.runner_display,
                runner_twitch=p0.twitch if p0 else r.runner_twitch,
                runner_discord=p0.discord if p0 else r.runner_discord,
                runner_slug=p0.slug if p0 else runner_slug(r.runner_twitch, r.runner_display, 0),
                incentive_text=r.incentive_text,
                incentive_category=r.incentive_category,
                valid_for_game=r.valid_for_game,
                incentive_estimate=r.incentive_estimate,
                needs_approval=r.needs_approval,
                status=r.status,
                submission_id=r.submission_id,
                uuid=r.uuid,
                run_slug=slug,
                participants=participants,
            ))

        return result

    def spreadsheet_age(self) -> StaleInfo:
        from src.xlsx_reader import check_stale
        raw = check_stale(self._path, max_age_hours=self._max_stale_hours)
        return StaleInfo(**raw)

    def incentive(self, uuid: str) -> Optional[IncentiveDTO]:
        """Look up a single incentive by uuid. Read-only; no editing."""
        for inc in self.incentives():
            if inc.uuid == uuid:
                return inc
        return None

    def patch_incentive(self, uuid: str, patch) -> Optional[IncentiveDTO]:
        """Not supported on xlsx repo. The xlsx is a raw source; edits
        must go through the SQLite repo."""
        raise NotImplementedError(
            "Incentive editing requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and not editable."
        )

    def create_incentive(self, body) -> IncentiveDTO:
        raise NotImplementedError(
            "Incentive creation requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and not editable."
        )

    def delete_incentive(self, uuid: str) -> Optional[IncentiveDTO]:
        raise NotImplementedError(
            "Incentive deletion requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and not editable."
        )

    def runner(self, slug: str) -> Optional[RunnerDTO]:
        raise NotImplementedError(
            "Runner lookup requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and does not support runner entities."
        )

    def runner_profile(self, slug: str) -> Optional[RunnerProfileDTO]:
        raise NotImplementedError(
            "Runner profile requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and does not support runner entities."
        )

    def runner_pbs(self, slug: str) -> Optional[RunnerPBDTO]:
        raise NotImplementedError(
            "Runner PBs requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and does not support runner entities."
        )

    def runner_runs(self, slug: str, limit: int = 5) -> list[RunDTO]:
        raise NotImplementedError(
            "Runner runs lookup requires REPO_TYPE=sqlite. The xlsx is a "
            "raw import source and does not support runner entities."
        )

    def create_job(self, kind: str, target: str = "") -> JobDTO:
        raise NotImplementedError("create_job requires REPO_TYPE=sqlite")

    def get_job(self, id: str) -> Optional[JobDTO]:
        raise NotImplementedError("get_job requires REPO_TYPE=sqlite")

    def list_jobs(self, kind: str = "", status: str = "", limit: int = 50) -> list[JobDTO]:
        raise NotImplementedError("list_jobs requires REPO_TYPE=sqlite")

    def update_job(self, id: str, status: str = "", summary_json: str = "", error: str = "", completed_at: Optional[datetime] = None) -> Optional[JobDTO]:
        raise NotImplementedError("update_job requires REPO_TYPE=sqlite")

    def cancel_job(self, id: str) -> Optional[JobDTO]:
        raise NotImplementedError("cancel_job requires REPO_TYPE=sqlite")

    def update_runner(self, slug: str, patch: dict) -> Optional[RunnerDTO]:
        raise NotImplementedError("update_runner requires REPO_TYPE=sqlite")

    def update_run(self, slug: str, patch: dict) -> Optional[RunDTO]:
        raise NotImplementedError("update_run requires REPO_TYPE=sqlite")

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class JobDTO(BaseModel):
    id: str
    kind: str
    status: str
    target: str
    summary_json: str
    error: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class JobAlreadyRunningError(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id


class ParticipantDTO(BaseModel):
    slug: str = ""
    display_name: str = ""
    twitch: str = ""
    discord: str = ""
    twitter: str = ""
    pronouns: str = ""
    pronunciation: str = ""
    submission_id: Optional[str] = None
    match_confidence: str = ""


class RunDTO(BaseModel):
    pick: int
    scheduled: datetime
    game: str
    category: str
    estimate: str
    estimate_seconds: int = 0
    platform: str
    players: str
    # Flat fields preserved for transitional frontend compatibility.
    # Populated from participants[0] when multiple runners exist.
    runner_display: str
    runner_twitch: str
    runner_discord: str
    runner_twitter: str
    runner_slug: str = ""
    note: Optional[str] = None
    layout: Optional[str] = None
    stream: str
    stream_short: str
    submission_id: Optional[str] = None
    category_id: Optional[str] = None
    incentives: str = ""
    commentator: str = ""
    upload_speed: str = ""
    pronouns: str = ""
    show_cam: str = ""
    runner_comments: str = ""
    slug: str = ""
    participants: list[ParticipantDTO] = []


class IncentiveDTO(BaseModel):
    scheduled: datetime
    game: str
    category: str
    stream: str
    # Flat fields preserved for transitional compatibility.
    runner_display: str
    runner_twitch: str
    runner_discord: str
    runner_slug: str = ""
    incentive_text: str
    details: str = ""
    incentive_category: str
    valid_for_game: str
    incentive_estimate: str
    needs_approval: str
    status: str
    submission_id: str
    uuid: str
    run_slug: str = ""
    participants: list[ParticipantDTO] = []


class BriefSidecarSource(BaseModel):
    name: str
    url: str = ""


class BriefSidecarIncentive(BaseModel):
    category: str  # Reward / Poll-Bid War / Target
    description: str
    estimate: str = ""


class BriefSidecarSibling(BaseModel):
    scheduled: str
    game: str
    category: str
    estimate: str
    stream: str
    is_next: bool = False


class BriefSidecarCategoryRecord(BaseModel):
    place: int
    runner: str
    time: str
    date: Optional[str] = None


class BriefSidecarCategoryInfo(BaseModel):
    name: str
    wr_holder: str = ""
    wr_time: str = ""
    wr_date: str = ""
    records: list[BriefSidecarCategoryRecord] = []


class BriefSidecar(BaseModel):
    slug: str
    scheduled: str
    mode: str = "scan"
    run_meta: dict = {}
    incentives: list[BriefSidecarIncentive] = []
    runner_section: Optional[dict] = None
    category_section: Optional[BriefSidecarCategoryInfo] = None
    game_section: Optional[dict] = None
    interview_material: list[str] = []
    siblings: list[BriefSidecarSibling] = []
    sources: list[BriefSidecarSource] = []
    confidence_flags: list[str] = []


class BriefResponse(BaseModel):
    slug: str
    prose_md: str
    sidecar: Optional[BriefSidecar] = None
    source: str = "markdown-only"


class BriefIndexEntry(BaseModel):
    slug: str
    title: str
    scheduled: str
    summary_line: str


class BriefIndexResponse(BaseModel):
    index_md_html: str
    runs: list[BriefIndexEntry]


class StaleInfo(BaseModel):
    age_hours: Optional[float] = None
    is_stale: bool = False
    is_missing: bool = False


class IncentivePatch(BaseModel):
    """Editable fields on an incentive. All optional — only set fields are updated."""

    incentive_text: Optional[str] = None
    details: Optional[str] = None
    incentive_category: Optional[str] = None
    valid_for_game: Optional[str] = None
    status: Optional[str] = None
    incentive_estimate: Optional[str] = None


class RunnerDTO(BaseModel):
    slug: str
    display_name: str
    twitch: str
    discord: str
    twitter: str
    pronouns: str
    pronunciation: str = ""
    run_count: int = 0
    esa_count: int = 0
    first_esa: Optional[str] = None
    upcoming_runs: list[RunDTO] = []


class IncentiveCreateRequest(BaseModel):
    """Fields required to create a new incentive."""

    run_slug: str
    incentive_text: str
    details: str = ""
    incentive_category: str = ""
    valid_for_game: str = ""
    incentive_estimate: str = ""
    status: str = ""


class RunnerProfileDTO(BaseModel):
    """Composite runner profile with summary + detailed stats block.

    Returned by /api/runners/{slug}/profile. The `stats_json` column
    in the Runner table stores the JSON blob from `runner-profile`;
    this DTO wraps it with the runner's identity fields for the API.
    """

    slug: str
    display_name: str
    twitch: str
    discord: str
    twitter: str
    pronouns: str
    pronunciation: str = ""
    summary: Optional[dict] = None
    stats: Optional[dict] = None
    sources: list[dict] = []
    errors: list[str] = []
    has_profile: bool = False


class RunnerPBEntry(BaseModel):
    game: str = ""
    category: str = ""
    time: str = ""
    platform: str = ""
    verified: bool = False
    date: Optional[str] = None
    video: str = ""
    notes: str = ""


class RunnerPBDTO(BaseModel):
    slug: str
    display_name: str
    pbs: list[RunnerPBEntry] = []
    has_pbs: bool = False

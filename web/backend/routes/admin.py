"""Admin endpoints: refresh, restore, status, audit, hosts, jobs, sync.

All require a valid admin session cookie. See auth_admin.py.
"""

import json
import os
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import anyio
from fastapi import APIRouter, Depends, HTTPException, Response, Query, Request
from pydantic import BaseModel
from sqlmodel import Session, select, func

from .. import config
from ..auth_admin import (
    admin_cookie_name, create_admin_session, current_admin,
    verify_admin_password,
)
from ..deps import get_briefs_dir, get_repo
from ..limiter import limiter
from ..models import JobDTO, JobAlreadyRunningError, RunnerDTO, RunDTO
from ..repo import IncentiveRepo
from src import audit as audit_log
from src.db import (
    Host, Incentive, Note, Run, Run as DBRun, Snapshot as DBSnapshot,
    get_schema_version, init_db, quick_check,
)
from src import snapshot as snap
from src.import_to_sqlite import import_xlsx_to_sqlite
from src.pipeline import run_pipeline

router = APIRouter(prefix="/api/admin", tags=["admin"])

TZ = ZoneInfo("Europe/Stockholm")


# ── Sync workers ──

def _sync_schedule_worker(repo: IncentiveRepo, job_id: str) -> None:
    """Run the full pipeline + import, updating job status along the way."""
    try:
        repo.update_job(job_id, status="running")

        result = run_pipeline()

        import_result = import_xlsx_to_sqlite(config.SPREADSHEET_PATH, config.DB_PATH)

        summary = json.dumps([
            {"step": "pipeline", "detail": f"pulled {result.get('runs', 0)} runs, {result.get('incentives', 0)} incentives"},
            {"step": "import", "detail": f"imported {import_result.get('runs_added', 0)} runs, {import_result.get('incentives_added', 0)} incentives"},
        ])

        repo.update_job(job_id, status="succeeded", summary_json=summary, completed_at=datetime.now(TZ))
    except Exception as e:
        repo.update_job(job_id, status="failed", error=str(e), completed_at=datetime.now(TZ))


def _stub_work(repo: IncentiveRepo, job_id: str, kind: str, target: str = "") -> None:
    """Stub sync worker: sleeps 2s then marks succeeded."""
    import time
    time.sleep(2)
    repo.update_job(
        job_id,
        status="succeeded",
        summary_json='[{"step": "done", "detail": "Stub implementation"}]',
    )


def _sync_briefs_worker(repo: IncentiveRepo, job_id: str) -> None:
    """Regenerate briefs, updating job status along the way."""
    try:
        repo.update_job(job_id, status="running")
        from src.brief import generate_briefs
        result = generate_briefs()
        summary = json.dumps([{"step": "briefs", "detail": f"generated {result.get('count', 0)} briefs"}])
        repo.update_job(job_id, status="succeeded", summary_json=summary, completed_at=datetime.now(TZ))
    except Exception as e:
        repo.update_job(job_id, status="failed", error=str(e), completed_at=datetime.now(TZ))


def _sync_briefs_llm_worker(
    repo: IncentiveRepo,
    job_id: str,
    mode: str = "scan",
    refresh_runners: bool = False,
    slugs: list[str] | None = None,
    runner_twitches: list[str] | None = None,
) -> None:
    """Regenerate briefs using LLM prose authoring, updating job status."""
    try:
        repo.update_job(job_id, status="running")
        from src.brief import generate_briefs_llm
        result = generate_briefs_llm(
            mode=mode,
            refresh_runners=refresh_runners,
            slugs=slugs,
            runner_twitches=runner_twitches,
        )
        summary = json.dumps([{
            "step": "briefs_llm",
            "detail": (
                f"generated {result.get('count', 0)} briefs "
                f"(runner profiles updated: {result.get('runner_profiles_updated', 0)})"
            ),
        }])
        repo.update_job(job_id, status="succeeded", summary_json=summary, completed_at=datetime.now(TZ))
    except Exception as e:
        repo.update_job(job_id, status="failed", error=str(e), completed_at=datetime.now(TZ))


def _sync_runners_worker(repo: IncentiveRepo, job_id: str, target: str = "") -> None:
    """Research runner(s), updating job status along the way."""
    try:
        repo.update_job(job_id, status="running")
        from src.brief import research_runner
        result = research_runner(twitch=target)
        summary = json.dumps([{"step": "runner", "detail": f"researched {target or 'all runners'}"}])
        repo.update_job(job_id, status="succeeded", summary_json=summary, completed_at=datetime.now(TZ))
    except Exception as e:
        repo.update_job(job_id, status="failed", error=str(e), completed_at=datetime.now(TZ))


# ── Auth ──


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    ok: bool


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def admin_login(request: Request, body: LoginRequest, response: Response):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid admin password")
    session = create_admin_session()
    response.set_cookie(
        key=admin_cookie_name(),
        value=session,
        max_age=config.ADMIN_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=config.SECURE_COOKIES,
    )
    return LoginResponse(ok=True)


@router.post("/logout", response_model=LoginResponse)
async def admin_logout(response: Response, _=Depends(current_admin)):
    response.delete_cookie(key=admin_cookie_name())
    return LoginResponse(ok=True)


# ── Status ──


class DBStatus(BaseModel):
    db_size_bytes: int
    db_exists: bool
    db_healthy: bool
    schema_version: int
    last_import_at: Optional[str] = None
    counts: dict


@router.get("/status", response_model=DBStatus)
async def admin_status(_=Depends(current_admin)):
    db_path = config.DB_PATH
    output_dir = os.path.dirname(db_path)

    exists = os.path.exists(db_path)
    healthy = quick_check(db_path) if exists else False
    schema_v = get_schema_version(db_path) if exists else 0
    size = os.path.getsize(db_path) if exists else 0

    counts = {
        "runs": 0,
        "incentives": 0,
        "notes": 0,
        "hosts": 0,
        "snapshots": 0,
    }
    last_import = None

    if exists and healthy:
        from src.db import make_engine
        engine = make_engine(db_path)
        with Session(engine) as s:
            counts["runs"] = s.exec(select(func.count(DBRun.id))).one()
            counts["incentives"] = s.exec(select(func.count(Incentive.uuid))).one()
            counts["notes"] = s.exec(select(func.count(Note.id))).one()
            counts["hosts"] = s.exec(select(func.count(Host.id))).one()
            counts["snapshots"] = s.exec(select(func.count(DBSnapshot.id))).one()
            newest = s.exec(select(DBRun).order_by(DBRun.imported_at.desc())).first()
            if newest:
                last_import = newest.imported_at.isoformat()
        engine.dispose()

    counts["snapshots"] = len(snap.list_snapshots(db_path))

    return DBStatus(
        db_size_bytes=size,
        db_exists=exists,
        db_healthy=healthy,
        schema_version=schema_v,
        last_import_at=last_import,
        counts=counts,
    )


# ── Refresh ──


class RefreshResponse(BaseModel):
    ok: bool
    snapshot_id: Optional[str] = None
    runs_added: int
    runs_updated: int
    incentives_added: int
    incentives_updated: int
    error: Optional[str] = None


@router.post("/refresh", response_model=RefreshResponse)
async def admin_refresh(response: Response, _=Depends(current_admin)):
    db_path = config.DB_PATH
    output_dir = os.path.dirname(db_path)
    xlsx_path = config.SPREADSHEET_PATH

    # Pre-import snapshot
    snapshot_id = None
    if os.path.exists(db_path):
        schema_v = get_schema_version(db_path)
        info = snap.create_snapshot(db_path, schema_v, reason="pre-import")
        snapshot_id = info.id
        audit_log.write_audit(output_dir, "refresh", f"snapshot={info.id} pre-import")

    # Run the import
    try:
        result = import_xlsx_to_sqlite(xlsx_path, db_path)
    except Exception as e:
        audit_log.write_audit(output_dir, "refresh", f"FAILED: {e}")
        return RefreshResponse(
            ok=False,
            error=str(e),
            runs_added=0, runs_updated=0,
            incentives_added=0, incentives_updated=0,
        )

    # Prune old snapshots
    pruned = snap.prune_snapshots(db_path, keep=config.SNAPSHOT_KEEP)
    if pruned:
        audit_log.write_audit(output_dir, "refresh", f"pruned {pruned} old snapshots")

    audit_log.write_audit(
        output_dir, "refresh",
        f"runs +{result.get('runs_added', 0)} ~{result.get('runs_updated', 0)} "
        f"incentives +{result.get('incentives_added', 0)} ~{result.get('incentives_updated', 0)}",
    )

    return RefreshResponse(
        ok=True,
        snapshot_id=snapshot_id,
        runs_added=result.get("runs_added", 0),
        runs_updated=result.get("runs_updated", 0),
        incentives_added=result.get("incentives_added", 0),
        incentives_updated=result.get("incentives_updated", 0),
    )


# ── Snapshots ──


class SnapshotDTO(BaseModel):
    id: str
    size_bytes: int
    age_hours: float
    schema_version: int


@router.get("/snapshots", response_model=list[SnapshotDTO])
async def admin_snapshots(_=Depends(current_admin)):
    snaps = snap.list_snapshots(config.DB_PATH)
    return [
        SnapshotDTO(
            id=s.id, size_bytes=s.size_bytes,
            age_hours=s.age_hours, schema_version=s.schema_version,
        )
        for s in snaps
    ]


class RestoreRequest(BaseModel):
    snapshot_id: str


_SNAPSHOT_ID_RE = re.compile(r"^\d{8}T\d{6}$")


@router.post("/restore", response_model=RefreshResponse)
async def admin_restore(body: RestoreRequest, _=Depends(current_admin)):
    if not _SNAPSHOT_ID_RE.match(body.snapshot_id):
        raise HTTPException(status_code=400, detail="Invalid snapshot_id format")
    db_path = config.DB_PATH
    output_dir = os.path.dirname(db_path)

    # Pre-restore snapshot
    if os.path.exists(db_path):
        schema_v = get_schema_version(db_path)
        pre = snap.create_snapshot(db_path, schema_v, reason="pre-restore")
        audit_log.write_audit(output_dir, "restore", f"snapshot={pre.id} pre-restore")

    # Restore
    try:
        info = snap.restore_snapshot(db_path, body.snapshot_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Verify after restore
    if not quick_check(db_path):
        audit_log.write_audit(output_dir, "restore", f"FAILED: DB failed quick_check after restoring {body.snapshot_id}")
        raise HTTPException(status_code=500, detail="DB failed integrity check after restore")

    pruned = snap.prune_snapshots(db_path, keep=config.SNAPSHOT_KEEP)
    if pruned:
        audit_log.write_audit(output_dir, "restore", f"pruned {pruned} old snapshots")
    audit_log.write_audit(output_dir, "restore", f"restored from {body.snapshot_id}")

    return RefreshResponse(
        ok=True,
        snapshot_id=body.snapshot_id,
        runs_added=0, runs_updated=0,
        incentives_added=0, incentives_updated=0,
    )


# ── Audit log ──


class AuditEntry(BaseModel):
    timestamp: str
    action: str
    detail: str


@router.get("/audit", response_model=list[AuditEntry])
async def admin_audit(_=Depends(current_admin), limit: int = 50):
    output_dir = os.path.dirname(config.DB_PATH)
    raw = audit_log.read_audit(output_dir, limit=limit)
    result = []
    for line in raw:
        parts = line.split(" | ", 2)
        if len(parts) == 3:
            result.append(AuditEntry(
                timestamp=parts[0], action=parts[1], detail=parts[2],
            ))
    return result


# ── Hosts ──


class HostDTO(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: str


class HostCreateRequest(BaseModel):
    name: str


@router.get("/hosts", response_model=list[HostDTO])
async def admin_list_hosts(_=Depends(current_admin)):
    db_path = config.DB_PATH
    if not os.path.exists(db_path):
        return []
    from src.db import make_engine
    engine = make_engine(db_path)
    with Session(engine) as s:
        hosts = s.exec(select(Host).order_by(Host.name)).all()
    engine.dispose()
    return [
        HostDTO(id=h.id, name=h.name, is_active=h.is_active, created_at=h.created_at.isoformat())
        for h in hosts
    ]


@router.post("/hosts", response_model=HostDTO)
async def admin_create_host(body: HostCreateRequest, _=Depends(current_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name too long")
    from src.db import make_engine
    from datetime import datetime
    from zoneinfo import ZoneInfo
    engine = make_engine(config.DB_PATH)
    try:
        with Session(engine) as s:
            existing = s.exec(select(Host).where(Host.name == name)).first()
            if existing is not None:
                if existing.is_active:
                    raise HTTPException(status_code=409, detail="Host with that name already exists")
                # Re-activate the soft-deleted host
                existing.is_active = True
                s.add(existing)
                s.commit()
                s.refresh(existing)
                audit_log.write_audit(
                    os.path.dirname(config.DB_PATH), "host_reactivate",
                    f"id={existing.id} name={existing.name}",
                )
                return HostDTO(
                    id=existing.id, name=existing.name,
                    is_active=existing.is_active,
                    created_at=existing.created_at.isoformat(),
                )
            host = Host(
                name=name,
                is_active=True,
                created_at=datetime.now(ZoneInfo("Europe/Stockholm")).replace(tzinfo=None),
            )
            s.add(host)
            s.commit()
            s.refresh(host)
            audit_log.write_audit(
                os.path.dirname(config.DB_PATH), "host_create",
                f"id={host.id} name={host.name}",
            )
            return HostDTO(
                id=host.id, name=host.name,
                is_active=host.is_active,
                created_at=host.created_at.isoformat(),
            )
    finally:
        engine.dispose()


@router.delete("/hosts/{host_id}")
async def admin_deactivate_host(host_id: int, _=Depends(current_admin)):
    from src.db import make_engine
    engine = make_engine(config.DB_PATH)
    try:
        with Session(engine) as s:
            host = s.get(Host, host_id)
            if host is None:
                raise HTTPException(status_code=404, detail="Host not found")
            # Soft delete: flip is_active off. Existing notes keep
            # their denormalized host_name.
            host.is_active = False
            s.add(host)
            s.commit()
            s.refresh(host)
            audit_log.write_audit(
                os.path.dirname(config.DB_PATH), "host_deactivate",
                f"id={host_id} name={host.name}",
            )
            return {"ok": True, "id": host_id}
    finally:
        engine.dispose()


# ── Jobs ──


@router.get("/jobs", response_model=list[JobDTO])
async def list_jobs(
    kind: str = "",
    status: str = "",
    limit: int = 50,
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    return repo.list_jobs(kind=kind, status=status, limit=limit)


@router.get("/jobs/{id}", response_model=JobDTO)
async def get_job(
    id: str,
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    job = repo.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{id}/cancel", response_model=JobDTO)
async def cancel_job(
    id: str,
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    job = repo.cancel_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── Sync stubs ──


@router.post("/sync/schedule", response_model=JobDTO)
async def sync_schedule(
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    try:
        job = repo.create_job(kind="schedule")
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=f"Schedule sync already running (job {exc.job_id})")
    await anyio.to_thread.run_sync(_sync_schedule_worker, repo, job.id)
    return repo.get_job(job.id)


@router.post("/sync/briefs", response_model=JobDTO)
async def sync_briefs(
    engine: str = Query(default="deterministic", description="'deterministic' or 'llm'"),
    mode: str = Query(default="scan", description="Brief mode for LLM engine: scan | interview | full"),
    runners: bool = Query(default=False, description="Refresh runner profiles before generating (LLM engine only)"),
    slugs: str = Query(default="", description="Comma-separated run slugs to target (LLM engine only). Empty = all runs."),
    runner_filter: str = Query(default="", alias="runner", description="Comma-separated Twitch handles to target (LLM engine only). Empty = all runners."),
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    try:
        job = repo.create_job(kind="briefs")
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=f"Briefs sync already running (job {exc.job_id})")

    if engine == "llm":
        slug_list = [s.strip() for s in slugs.split(",") if s.strip()] or None
        twitch_list = [t.strip().lower() for t in runner_filter.split(",") if t.strip()] or None
        await anyio.to_thread.run_sync(
            lambda: _sync_briefs_llm_worker(
                repo, job.id,
                mode=mode,
                refresh_runners=runners,
                slugs=slug_list,
                runner_twitches=twitch_list,
            )
        )
    else:
        await anyio.to_thread.run_sync(_sync_briefs_worker, repo, job.id)

    return repo.get_job(job.id)


@router.post("/sync/runners", response_model=JobDTO)
async def sync_runners(
    slug: str = Query(default=""),
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    try:
        job = repo.create_job(kind="runners", target=slug)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=f"Runners sync already running (job {exc.job_id})")
    await anyio.to_thread.run_sync(_sync_runners_worker, repo, job.id, slug)
    return repo.get_job(job.id)


# ── Runner / Run editing ──


class RunnerPatchRequest(BaseModel):
    display_name: Optional[str] = None
    twitch: Optional[str] = None
    discord: Optional[str] = None
    twitter: Optional[str] = None
    pronouns: Optional[str] = None
    pronunciation: Optional[str] = None


class RunPatchRequest(BaseModel):
    commentator: Optional[str] = None
    pronouns: Optional[str] = None
    show_cam: Optional[str] = None
    runner_comments: Optional[str] = None
    runner_slugs: Optional[list[str]] = None


@router.patch("/runners/{slug}", response_model=RunnerDTO)
async def admin_patch_runner(
    slug: str,
    body: RunnerPatchRequest,
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = repo.update_runner(slug, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Runner not found")
    return result


@router.patch("/runs/{slug}", response_model=RunDTO)
async def admin_patch_run(
    slug: str,
    body: RunPatchRequest,
    _=Depends(current_admin),
    repo: IncentiveRepo = Depends(get_repo),
):
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = repo.update_run(slug, patch)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_repo, auth_required
from ..repo import IncentiveRepo

router = APIRouter(tags=["runners"])


@router.get("/api/runners")
async def list_runners(
    repo: IncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    return repo.runners()


@router.get("/api/runners/{slug}")
async def get_runner(
    slug: str,
    repo: IncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    runner = repo.runner(slug)
    if runner is None:
        raise HTTPException(status_code=404, detail="Runner not found")
    return runner


@router.get("/api/runners/{slug}/profile")
async def get_runner_profile(
    slug: str,
    repo: IncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    """Return the composite runner profile (summary + stats block).

    The profile is populated during xlsx→SQLite import from the
    on-disk runner-profile cache. If `has_profile` is false, the
    caller should trigger a `runner-profile` CLI call and re-import.
    """
    profile = repo.runner_profile(slug)
    if profile is None:
        raise HTTPException(status_code=404, detail="Runner not found")
    return profile


@router.get("/api/runners/{slug}/pbs")
async def get_runner_pbs(
    slug: str,
    repo: IncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    pbs = repo.runner_pbs(slug)
    if pbs is None:
        raise HTTPException(status_code=404, detail="Runner not found")
    return pbs


@router.get("/api/runners/{slug}/runs")
async def get_runner_runs(
    slug: str,
    repo: IncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    return repo.runner_runs(slug)

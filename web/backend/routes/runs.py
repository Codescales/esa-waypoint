from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_repo, auth_required
from ..repo import XlsxIncentiveRepo

router = APIRouter(tags=["runs"])


@router.get("/api/runs")
async def list_runs(
    stream: str = Query(default=""),
    window: str = Query(default=""),
    next_hours: float = Query(default=0),
    marathon: bool = Query(default=False),
    repo: XlsxIncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    parsed_window = None
    if window:
        parts = window.split("/")
        if len(parts) == 2:
            try:
                parsed_window = (datetime.fromisoformat(parts[0]), datetime.fromisoformat(parts[1]))
            except ValueError:
                pass
    return repo.runs(stream=stream, window=parsed_window, next_hours=next_hours, marathon=marathon)


@router.get("/api/runs/{slug}")
async def get_run(
    slug: str,
    repo: XlsxIncentiveRepo = Depends(get_repo),
    _=auth_required,
):
    run = repo.run(slug)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Run not found")
    return run

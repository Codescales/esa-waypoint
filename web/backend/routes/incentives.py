import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from .. import config
from ..auth_admin import admin_cookie_name, current_admin, validate_admin_session
from ..deps import get_repo
from ..models import IncentiveDTO, IncentivePatch, IncentiveCreateRequest
from ..repo import IncentiveRepo
from src import audit as audit_log

router = APIRouter(tags=["incentives"])


@router.get("/api/incentives", response_model=list[IncentiveDTO])
async def list_incentives(
    run_slug: str = Query(default=""),
    status: str = Query(default=""),
    category: str = Query(default=""),
    stream: str = Query(default=""),
    repo: IncentiveRepo = Depends(get_repo),
):
    return repo.incentives(run_slug=run_slug, status=status, category=category, stream=stream)


@router.get("/api/incentives/{uuid}", response_model=IncentiveDTO)
async def get_incentive(
    uuid: str,
    repo: IncentiveRepo = Depends(get_repo),
):
    inc = repo.incentive(uuid)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incentive not found")
    return inc


@router.patch("/api/incentives/{uuid}", response_model=IncentiveDTO)
async def patch_incentive(
    uuid: str,
    patch: IncentivePatch,
    repo: IncentiveRepo = Depends(get_repo),
    esa_admin_session: str | None = Cookie(default=None, alias="esa_admin_session"),
):
    is_admin = validate_admin_session(esa_admin_session)

    # Unauthenticated PATCH must not set status or valid_for_game
    # (those fields flow into the Tiltify push set).
    if not is_admin:
        data = patch.model_dump(exclude_unset=True) if hasattr(patch, "model_dump") else patch.dict(exclude_unset=True)
        if "status" in data or "valid_for_game" in data:
            raise HTTPException(
                status_code=422,
                detail="Setting status or valid_for_game requires admin authentication",
            )

    try:
        inc = repo.patch_incentive(uuid, patch)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    if inc is None:
        raise HTTPException(status_code=404, detail="Incentive not found")

    audit_log.write_audit(
        os.path.dirname(config.DB_PATH),
        "incentive_patch",
        f"uuid={uuid}",
    )
    return inc


@router.post("/api/incentives", response_model=IncentiveDTO, status_code=201)
async def create_incentive(
    body: IncentiveCreateRequest,
    repo: IncentiveRepo = Depends(get_repo),
    _=Depends(current_admin),
):
    try:
        inc = repo.create_incentive(body)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    audit_log.write_audit(
        os.path.dirname(config.DB_PATH),
        "incentive_create",
        f"run={body.run_slug} text={body.incentive_text[:60]}",
    )
    return inc


@router.delete("/api/incentives/{uuid}", response_model=IncentiveDTO)
async def delete_incentive(
    uuid: str,
    repo: IncentiveRepo = Depends(get_repo),
    _=Depends(current_admin),
):
    try:
        inc = repo.delete_incentive(uuid)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    if inc is None:
        raise HTTPException(status_code=404, detail="Incentive not found")

    audit_log.write_audit(
        os.path.dirname(config.DB_PATH),
        "incentive_delete",
        f"uuid={uuid}",
    )
    return inc

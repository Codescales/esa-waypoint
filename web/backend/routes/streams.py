from fastapi import APIRouter, Depends

from ..deps import get_repo, auth_required
from ..repo import XlsxIncentiveRepo

router = APIRouter(tags=["streams"])


@router.get("/api/streams")
async def list_streams(repo: XlsxIncentiveRepo = Depends(get_repo), _=auth_required):
    return repo.streams()

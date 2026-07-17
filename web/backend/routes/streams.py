from fastapi import APIRouter, Depends

from ..deps import get_repo
from ..repo import XlsxIncentiveRepo

router = APIRouter(tags=["streams"])


@router.get("/api/streams")
async def list_streams(repo: XlsxIncentiveRepo = Depends(get_repo)):
    return repo.streams()

from fastapi import APIRouter, Depends

from ..deps import get_repo
from ..repo import XlsxIncentiveRepo

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(repo: XlsxIncentiveRepo = Depends(get_repo)):
    return repo.spreadsheet_age()

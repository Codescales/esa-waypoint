from fastapi import APIRouter, Depends, Query

from ..deps import get_repo
from ..models import NewsItemDTO
from ..repo import IncentiveRepo

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=list[NewsItemDTO])
async def list_news(
    limit: int = Query(default=50, ge=1, le=200),
    repo: IncentiveRepo = Depends(get_repo),
):
    return repo.list_news(limit=limit)

"""FastAPI dependency injection for shared objects."""

from fastapi import Request, Depends

from .auth import current_session
from .config import BRIEFS_DIR, DB_PATH, REPO_TYPE, SPREADSHEET_PATH
from .repo import XlsxIncentiveRepo


def get_repo(request: Request):
    """Return the active repo based on REPO_TYPE env var.

    The repo is initialized once at app startup (lifespan) and stored
    on app.state. Selection happens there, not here.
    """
    return request.app.state.repo


def get_briefs_dir() -> str:
    return BRIEFS_DIR


auth_required = Depends(current_session)


__all__ = ["get_repo", "get_briefs_dir", "auth_required", "REPO_TYPE", "DB_PATH", "SPREADSHEET_PATH"]

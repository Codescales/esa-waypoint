"""FastAPI app for ESA host brief web viewer."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from . import config
from .repo import XlsxIncentiveRepo
from .repo_sqlite import SqliteIncentiveRepo
from .routes import health, auth as auth_routes, streams, runs, incentives, briefs
from .routes import admin as admin_routes
from .routes import notes as notes_routes
from .routes import runner_notes as runner_notes_routes
from .routes import runners as runners_routes
from src.db import init_db, orphan_job_sweep

_STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.REPO_TYPE == "sqlite":
        app.state.repo = SqliteIncentiveRepo(config.DB_PATH)
        init_db(config.DB_PATH)
        orphan_job_sweep(config.DB_PATH)
    else:
        app.state.repo = XlsxIncentiveRepo(config.SPREADSHEET_PATH)
    yield


app = FastAPI(title="ESA Host Brief Viewer", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_routes.router)
app.include_router(streams.router)
app.include_router(runs.router)
app.include_router(incentives.router)
app.include_router(briefs.router)
app.include_router(notes_routes.router)
app.include_router(runner_notes_routes.router)
app.include_router(admin_routes.router)
app.include_router(runners_routes.router)


# ── AI / tool discovery endpoints ────────────────────────────────────────────

@app.get(
    "/openapi.yaml",
    include_in_schema=False,
    summary="OpenAPI 3.1 spec (YAML)",
)
async def openapi_yaml():
    """Machine-readable OpenAPI 3.1 spec for tools and AI agents."""
    return FileResponse(
        _STATIC / "openapi.yaml",
        media_type="application/yaml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get(
    "/llms.txt",
    include_in_schema=False,
    summary="Plain-text context for AI agents (llms.txt convention)",
)
async def llms_txt():
    """Natural-language API context document following the llms.txt convention."""
    return PlainTextResponse(
        (_STATIC / "llms.txt").read_text(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


def main():
    import uvicorn
    uvicorn.run("web.backend.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()

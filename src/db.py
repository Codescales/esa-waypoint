"""SQLite database layer — SQLModel engine, schema, and helpers.

The schema mirrors the xlsx_reader dataclasses plus Phase 2 additions
(host, note, snapshot, audit). The schema_version pragma lets us gate
migrations cleanly.

Concurrency: SQLite serializes writes via file locking. We use WAL mode
for better read concurrency and `synchronous=NORMAL` for crash safety
without the full-sync penalty. See PRD-phase2 risk 5.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine, text


SCHEMA_VERSION = 5


class Run(SQLModel, table=True):
    __tablename__ = "run"

    id: Optional[int] = Field(default=None, primary_key=True)
    pick: int
    scheduled: datetime
    game: str
    category: str
    estimate: str
    estimate_seconds: int = 0
    platform: str = ""
    players: str = ""
    note: Optional[str] = None
    layout: Optional[str] = None
    stream: str
    stream_short: str
    submission_id: Optional[str] = None
    category_id: Optional[str] = None
    incentives: str = ""
    commentator: str = ""
    upload_speed: str = ""
    pronouns: str = ""
    show_cam: str = ""
    runner_comments: str = ""
    slug: str = Field(index=True)
    run_key: str = Field(unique=True, index=True)
    imported_at: datetime
    updated_at: datetime


class RunParticipant(SQLModel, table=True):
    __tablename__ = "run_participant"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    runner_slug: str = Field(index=True)
    display_name: str = ""
    twitch: str = ""
    discord: str = ""
    twitter: str = ""
    pronouns: str = ""
    pronunciation: str = ""
    submission_id: Optional[str] = None
    match_confidence: str = ""
    imported_at: datetime
    updated_at: datetime


class Incentive(SQLModel, table=True):
    __tablename__ = "incentive"

    uuid: str = Field(primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    scheduled: datetime
    game: str
    category: str
    stream: str
    participants_json: str = ""
    incentive_text: str
    incentive_category: str = ""
    valid_for_game: str = ""
    incentive_estimate: str = ""
    needs_approval: str = ""
    status: str = ""
    submission_id: str = ""
    imported_at: datetime
    updated_at: datetime


class Host(SQLModel, table=True):
    __tablename__ = "host"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    is_active: bool = True
    created_at: datetime


class Note(SQLModel, table=True):
    __tablename__ = "note"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    host_id: int = Field(foreign_key="host.id")
    host_name: str
    body: str
    created_at: datetime
    updated_at: datetime


class RunnerNote(SQLModel, table=True):
    __tablename__ = "runner_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    runner_slug: str = Field(index=True)
    host_id: int = Field(foreign_key="host.id")
    host_name: str
    body: str
    created_at: datetime
    updated_at: datetime


class Snapshot(SQLModel, table=True):
    __tablename__ = "snapshot"

    id: str = Field(primary_key=True)
    path: str
    size_bytes: int
    reason: str
    created_at: datetime
    schema_version: int


class Runner(SQLModel, table=True):
    __tablename__ = "runner"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    display_name: str = ""
    twitch: str = ""
    discord: str = ""
    twitter: str = ""
    src_user_id: str = ""
    src_url: str = ""
    pronouns: str = ""
    pronunciation: str = ""
    last_synced_at: Optional[datetime] = None
    src_payload_json: str = ""
    pbs_json: str = ""
    stats_json: str = ""  # JSON blob from runner-profile (summary + stats block)
    created_at: datetime
    updated_at: datetime


class Job(SQLModel, table=True):
    __tablename__ = "job"

    id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    status: str = Field(index=True)
    target: str = ""
    summary_json: str = ""
    error: str = ""
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


def parse_estimate_to_seconds(estimate: str) -> int:
    """Parse an estimate string (HH:MM:SS or MM:SS) to total seconds.

    Returns 0 for empty/malformed strings.
    """
    if not estimate or not estimate.strip():
        return 0
    parts = estimate.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except (ValueError, IndexError):
        return 0
    return 0


def orphan_job_sweep(db_path: str) -> None:
    """Mark any pending/running jobs as failed at boot.

    Prevents uvicorn --reload from permanently 409-locking a job kind.
    """
    engine = make_engine(db_path)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE job SET status='failed', error='interrupted at boot', "
                    "completed_at=:now WHERE status IN ('pending', 'running')"
                ),
                {"now": datetime.now().isoformat()},
            )
            conn.commit()
    except Exception:
        pass
    finally:
        engine.dispose()


def make_engine(db_path: str):
    """Build a SQLAlchemy engine with WAL mode and NORMAL synchronous.

    `check_same_thread=False` lets FastAPI's threadpool share the
    connection. SQLModel/SQLAlchemy 2.0 handles per-thread connections
    internally when `poolclass=StaticPool` is used, but for our usage
    the default pool with check_same_thread=False is fine.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def init_db(db_path: str) -> None:
    """Create tables, run migrations, stamp schema_version, and seed default data.

    Idempotent. Handles:
    - v1→v2: adds Run.estimate_seconds, partial unique index on Job
    - v2→v3: adds Runner.stats_json
    - v3→v4: drops flat runner_* columns from run/incentive, adds RunParticipant
      table with UNIQUE(run_id, runner_slug). Destructive for run/incentive rows
      (re-import required). Existing snapshot covers backup.
    - v4→v5: adds pronunciation column to run_participant and runner
    Seeding only happens on a fresh DB (no hosts present).
    """
    engine = make_engine(db_path)
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        existing = conn.execute(text("PRAGMA user_version")).scalar()

        if existing == 0:
            # Fresh DB — stamp to current version
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS job_kind_running_uniq "
                "ON job (kind) WHERE status IN ('pending', 'running')"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS run_participant_run_slug_uniq "
                "ON run_participant (run_id, runner_slug)"
            ))
            conn.commit()
            from sqlmodel import Session, select
            with Session(engine) as s:
                has_hosts = s.exec(select(Host)).first()
                if has_hosts is None:
                    s.add(Host(
                        name="Anonymous Host",
                        is_active=True,
                        created_at=datetime.now(__import__("zoneinfo").ZoneInfo("Europe/Stockholm")).replace(tzinfo=None),
                    ))
                    s.commit()
        elif existing == 1:
            # v1 → v2: add Run.estimate_seconds
            cols = conn.execute(text("PRAGMA table_info(run)")).fetchall()
            col_names = {c[1] for c in cols}
            if "estimate_seconds" not in col_names:
                conn.execute(text(
                    "ALTER TABLE run ADD COLUMN estimate_seconds INTEGER NOT NULL DEFAULT 0"
                ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS job_kind_running_uniq "
                "ON job (kind) WHERE status IN ('pending', 'running')"
            ))
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
            conn.commit()
        elif existing == 2:
            # v2 → v3: add Runner.stats_json
            cols = conn.execute(text("PRAGMA table_info(runner)")).fetchall()
            col_names = {c[1] for c in cols}
            if "stats_json" not in col_names:
                conn.execute(text(
                    "ALTER TABLE runner ADD COLUMN stats_json TEXT NOT NULL DEFAULT ''"
                ))
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
            conn.commit()
        elif existing == 3:
            # v3 → v4: drop flat runner_* from run/incentive, add run_participant.
            # Destructive for run/incentive rows — caller must re-import xlsx.
            import sys
            print(
                "  DB schema v3 → v4: dropping run/incentive rows and adding "
                "run_participant table. Re-import xlsx after this migration.",
                file=sys.stderr,
            )
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("DELETE FROM incentive"))
            conn.execute(text("DELETE FROM run"))
            # Recreate run without runner_* columns (SQLModel.metadata already
            # has the new schema; CREATE TABLE IF NOT EXISTS is a no-op for
            # tables that exist with the old schema, so we must drop and recreate).
            conn.execute(text("DROP TABLE IF EXISTS run_participant"))
            conn.execute(text("DROP TABLE IF EXISTS incentive"))
            conn.execute(text("DROP TABLE IF EXISTS run"))
            conn.commit()
            # Recreate with new schema
            SQLModel.metadata.create_all(engine)
            with engine.connect() as conn2:
                conn2.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS run_participant_run_slug_uniq "
                    "ON run_participant (run_id, runner_slug)"
                ))
                conn2.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
                conn2.execute(text("PRAGMA foreign_keys=ON"))
                conn2.commit()
        elif existing == 4:
            # v4 → v5: add pronunciation column to run_participant and runner
            cols = conn.execute(text("PRAGMA table_info(run_participant)")).fetchall()
            col_names = {c[1] for c in cols}
            if "pronunciation" not in col_names:
                conn.execute(text(
                    "ALTER TABLE run_participant ADD COLUMN pronunciation TEXT NOT NULL DEFAULT ''"
                ))
            cols = conn.execute(text("PRAGMA table_info(runner)")).fetchall()
            col_names = {c[1] for c in cols}
            if "pronunciation" not in col_names:
                conn.execute(text(
                    "ALTER TABLE runner ADD COLUMN pronunciation TEXT NOT NULL DEFAULT ''"
                ))
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
            conn.commit()

    engine.dispose()


def get_schema_version(db_path: str) -> int:
    """Read the schema version pragma. Returns 0 if DB doesn't exist."""
    import os
    if not os.path.exists(db_path):
        return 0
    engine = make_engine(db_path)
    with engine.connect() as conn:
        version = conn.execute(text("PRAGMA user_version")).scalar()
    engine.dispose()
    return int(version or 0)


def quick_check(db_path: str) -> bool:
    """Run PRAGMA quick_check. Returns True if DB is healthy."""
    import os
    if not os.path.exists(db_path):
        return False
    engine = None
    try:
        engine = make_engine(db_path)
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA quick_check")).fetchall()
            for row in result:
                if row[0] != "ok":
                    return False
            return True
    except Exception:
        return False
    finally:
        if engine is not None:
            engine.dispose()

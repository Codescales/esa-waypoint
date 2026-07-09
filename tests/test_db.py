import os
import tempfile
from datetime import datetime

from sqlmodel import Session, text, select, SQLModel

from src.db import (
    parse_estimate_to_seconds,
    make_engine,
    init_db,
    get_schema_version,
    quick_check,
    orphan_job_sweep,
    SCHEMA_VERSION,
    Run,
    RunParticipant,
    Incentive,
    Host,
    Note,
    RunnerNote,
    Snapshot,
    Runner,
    Job,
)


class TestParseEstimateToSeconds:
    def test_hh_mm_ss(self):
        assert parse_estimate_to_seconds("1:30:00") == 5400

    def test_mm_ss(self):
        assert parse_estimate_to_seconds("5:30") == 330

    def test_seconds_only(self):
        assert parse_estimate_to_seconds("300") == 300

    def test_empty(self):
        assert parse_estimate_to_seconds("") == 0

    def test_malformed(self):
        assert parse_estimate_to_seconds("abc") == 0

    def test_single_number(self):
        assert parse_estimate_to_seconds("42") == 42


class TestInitDb:
    def test_creates_tables(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            engine = make_engine(db_path)
            with engine.connect() as conn:
                tables = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )).fetchall()
                table_names = {r[0] for r in tables}
                for t in ("run", "incentive", "host", "note", "runner_note", "snapshot", "runner", "job", "run_participant"):
                    assert t in table_names, f"Missing table: {t}"
            engine.dispose()
        finally:
            os.unlink(db_path)

    def test_schema_version(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            assert get_schema_version(db_path) == SCHEMA_VERSION
        finally:
            os.unlink(db_path)

    def test_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            init_db(db_path)
            assert get_schema_version(db_path) == SCHEMA_VERSION
        finally:
            os.unlink(db_path)

    def test_seeds_default_host(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            engine = make_engine(db_path)
            with Session(engine) as s:
                hosts = s.exec(select(Host)).all()
                assert len(hosts) >= 1
                assert hosts[0].name == "Anonymous Host"
            engine.dispose()
        finally:
            os.unlink(db_path)

    def test_migration_v1_to_v5(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = make_engine(db_path)
            SQLModel.metadata.create_all(engine)
            with engine.connect() as conn:
                conn.execute(text("PRAGMA user_version = 1"))
                conn.commit()
            engine.dispose()
            init_db(db_path)
            assert get_schema_version(db_path) == SCHEMA_VERSION
        finally:
            os.unlink(db_path)

    def test_migration_v2_to_v5(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = make_engine(db_path)
            SQLModel.metadata.create_all(engine)
            with engine.connect() as conn:
                conn.execute(text("PRAGMA user_version = 2"))
                conn.commit()
            engine.dispose()
            init_db(db_path)
            assert get_schema_version(db_path) == SCHEMA_VERSION
        finally:
            os.unlink(db_path)

    def test_migration_v4_to_v5(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            engine = make_engine(db_path)
            SQLModel.metadata.create_all(engine)
            with engine.connect() as conn:
                conn.execute(text("PRAGMA user_version = 4"))
                conn.commit()
            engine.dispose()
            init_db(db_path)
            assert get_schema_version(db_path) == SCHEMA_VERSION
        finally:
            os.unlink(db_path)


class TestGetSchemaVersion:
    def test_nonexistent_db(self):
        assert get_schema_version("/nonexistent/path.db") == 0


class TestQuickCheck:
    def test_healthy_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            assert quick_check(db_path) is True
        finally:
            os.unlink(db_path)

    def test_nonexistent_db(self):
        assert quick_check("/nonexistent/path.db") is False


class TestOrphanJobSweep:
    def test_marks_pending_jobs(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            engine = make_engine(db_path)
            with Session(engine) as s:
                s.add(Job(
                    id="j1", kind="test", status="pending",
                    created_at=datetime.now(), updated_at=datetime.now(),
                ))
                s.commit()
            engine.dispose()
            orphan_job_sweep(db_path)
            engine = make_engine(db_path)
            with Session(engine) as s:
                job = s.get(Job, "j1")
                assert job.status == "failed"
            engine.dispose()
        finally:
            os.unlink(db_path)

    def test_no_pending_jobs(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            orphan_job_sweep(db_path)
        finally:
            os.unlink(db_path)

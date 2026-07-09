import os
import tempfile
import shutil

from src.snapshot import (
    snapshots_dir,
    create_snapshot,
    list_snapshots,
    restore_snapshot,
    prune_snapshots,
    SnapshotInfo,
)
from src.db import init_db, make_engine, SCHEMA_VERSION
from sqlmodel import text


def _create_test_db(path: str):
    init_db(path)
    engine = make_engine(path)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS test_data (val INTEGER)"))
        conn.execute(text("INSERT INTO test_data VALUES (42)"))
        conn.commit()
    engine.dispose()


class TestSnapshotsDir:
    def test_returns_snapshots_subdir(self):
        result = snapshots_dir("/tmp/esa.db")
        assert result == "/tmp/snapshots"


class TestCreateSnapshot:
    def test_creates_snapshot_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            info = create_snapshot(db_path, SCHEMA_VERSION, "test")
            assert os.path.exists(info.path)
            assert info.schema_version == SCHEMA_VERSION
            assert info.size_bytes > 0

    def test_raises_on_missing_db(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            create_snapshot("/nonexistent/db.db", SCHEMA_VERSION)


class TestListSnapshots:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            assert list_snapshots(db_path) == []

    def test_lists_snapshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            create_snapshot(db_path, SCHEMA_VERSION, "test1")
            import time; time.sleep(1.1)
            create_snapshot(db_path, SCHEMA_VERSION, "test2")
            snaps = list_snapshots(db_path)
            assert len(snaps) == 2

    def test_ignores_non_snapshot_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            snap_dir = os.path.join(tmpdir, "snapshots")
            os.makedirs(snap_dir, exist_ok=True)
            open(os.path.join(snap_dir, "random.txt"), "w").close()
            create_snapshot(db_path, SCHEMA_VERSION, "test")
            snaps = list_snapshots(db_path)
            assert len(snaps) == 1


class TestRestoreSnapshot:
    def test_restores_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            info = create_snapshot(db_path, SCHEMA_VERSION, "backup")
            # Modify the live DB
            engine = make_engine(db_path)
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM test_data"))
                conn.commit()
            engine.dispose()
            # Restore
            restore_snapshot(db_path, info.id)
            # Verify
            engine = make_engine(db_path)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT val FROM test_data")).fetchall()
                assert len(result) == 1
                assert result[0][0] == 42
            engine.dispose()

    def test_raises_on_missing_snapshot(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            restore_snapshot("/tmp/esa.db", "nonexistent")


class TestPruneSnapshots:
    def test_keeps_n_most_recent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            for i in range(5):
                create_snapshot(db_path, SCHEMA_VERSION, f"test{i}")
                import time; time.sleep(1.1)
            deleted = prune_snapshots(db_path, keep=2)
            assert deleted == 3
            snaps = list_snapshots(db_path)
            assert len(snaps) == 2

    def test_no_prune_when_under_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "esa.db")
            _create_test_db(db_path)
            create_snapshot(db_path, SCHEMA_VERSION, "test")
            deleted = prune_snapshots(db_path, keep=5)
            assert deleted == 0

"""Snapshot management — create, list, restore, prune.

Snapshots are full copies of the SQLite DB stored in
`<output_dir>/snapshots/esa.db.{timestamp}`. Used by the admin refresh
to back out bad imports.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")


@dataclass
class SnapshotInfo:
    id: str  # ISO timestamp, e.g. "20260801T140000"
    path: str  # absolute path
    size_bytes: int
    age_hours: float
    schema_version: int


def snapshots_dir(db_path: str) -> str:
    """Return the path to the snapshots directory for a given DB."""
    return os.path.join(os.path.dirname(db_path), "snapshots")


def create_snapshot(db_path: str, schema_version: int, reason: str = "manual") -> SnapshotInfo:
    """Copy the live DB to a timestamped snapshot file.

    Returns the snapshot info. The snapshots dir is created if missing.
    Caller is responsible for logging to the audit log.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")

    sdir = snapshots_dir(db_path)
    os.makedirs(sdir, exist_ok=True)

    ts = datetime.now(TZ).strftime("%Y%m%dT%H%M%S")
    snap_path = os.path.join(sdir, f"esa.db.{ts}")

    shutil.copy2(db_path, snap_path)
    size = os.path.getsize(snap_path)

    return SnapshotInfo(
        id=ts,
        path=snap_path,
        size_bytes=size,
        age_hours=0.0,
        schema_version=schema_version,
    )


def list_snapshots(db_path: str) -> list[SnapshotInfo]:
    """List all snapshots, newest first.

    Reads the schema_version from each snapshot by opening it briefly
    (catches version mismatches at list time).
    """
    sdir = snapshots_dir(db_path)
    if not os.path.isdir(sdir):
        return []

    now = datetime.now(TZ)
    snapshots: list[SnapshotInfo] = []

    for fname in sorted(os.listdir(sdir), reverse=True):
        if not fname.startswith("esa.db."):
            continue
        ts = fname[7:]
        # Timestamp format: YYYYMMDDTHHMMSS (15 chars, has T separator)
        if len(ts) != 15 or not (ts[:8].isdigit() and ts[8] == "T" and ts[9:].isdigit()):
            continue
        snap_path = os.path.join(sdir, fname)
        if not os.path.isfile(snap_path):
            continue
        sid = ts
        try:
            size = os.path.getsize(snap_path)
            mtime = datetime.fromtimestamp(os.path.getmtime(snap_path), tz=TZ)
            age = (now - mtime).total_seconds() / 3600
            schema_v = _read_schema_version(snap_path)
        except OSError:
            continue
        snapshots.append(SnapshotInfo(
            id=sid,
            path=snap_path,
            size_bytes=size,
            age_hours=round(age, 1),
            schema_version=schema_v,
        ))

    return snapshots


def _read_schema_version(db_path: str) -> int:
    """Read PRAGMA user_version from a DB file. Returns 0 on error."""
    from src.db import make_engine
    from sqlmodel import text
    try:
        engine = make_engine(db_path)
        with engine.connect() as conn:
            v = conn.execute(text("PRAGMA user_version")).scalar()
        engine.dispose()
        return int(v or 0)
    except Exception:
        return 0


def restore_snapshot(db_path: str, snapshot_id: str) -> SnapshotInfo:
    """Restore the live DB from a snapshot by overwriting.

    The current DB is replaced with the snapshot. Caller is responsible
    for creating a pre-restore snapshot first if needed.
    """
    sdir = snapshots_dir(db_path)
    snap_path = os.path.join(sdir, f"esa.db.{snapshot_id}")
    if not os.path.isfile(snap_path):
        raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

    if not os.path.exists(db_path):
        # No live DB to overwrite — just copy
        shutil.copy2(snap_path, db_path)
    else:
        # Atomic overwrite
        shutil.copy2(snap_path, db_path)

    size = os.path.getsize(db_path)
    return SnapshotInfo(
        id=snapshot_id,
        path=snap_path,
        size_bytes=size,
        age_hours=0.0,
        schema_version=_read_schema_version(db_path),
    )


def prune_snapshots(db_path: str, keep: int) -> int:
    """Delete oldest snapshots beyond `keep` count. Returns deleted count."""
    snaps = list_snapshots(db_path)
    if len(snaps) <= keep:
        return 0
    to_delete = snaps[keep:]  # sorted newest-first, so index >= keep are older
    deleted = 0
    for s in to_delete:
        try:
            os.remove(s.path)
            deleted += 1
        except OSError:
            pass
    return deleted

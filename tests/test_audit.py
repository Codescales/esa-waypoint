import os
import tempfile

from src.audit import audit_log_path, write_audit, read_audit


class TestAuditLogPath:
    def test_returns_joined_path(self):
        assert audit_log_path("/tmp/foo") == "/tmp/foo/admin_audit.log"


class TestWriteAndReadAudit:
    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_audit(tmpdir, "test-action", "test detail")
            entries = read_audit(tmpdir)
            assert len(entries) == 1
            assert "test-action" in entries[0]
            assert "test detail" in entries[0]

    def test_multiple_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_audit(tmpdir, "a", "1")
            write_audit(tmpdir, "b", "2")
            write_audit(tmpdir, "c", "3")
            entries = read_audit(tmpdir)
            assert len(entries) == 3

    def test_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                write_audit(tmpdir, f"action-{i}", f"detail-{i}")
            entries = read_audit(tmpdir, limit=3)
            assert len(entries) == 3
            assert "action-7" in entries[0]

    def test_no_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert read_audit(tmpdir) == []

    def test_write_creates_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "sub", "dir")
            write_audit(nested, "action", "detail")
            assert os.path.exists(audit_log_path(nested))

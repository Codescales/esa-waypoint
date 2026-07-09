"""Append-only audit log for admin actions.

Writes one line per action to `output/admin_audit.log`. Format:
    <ISO datetime> | <action> | <detail>

The log is intentionally simple — grep-friendly, no JSON wrapping.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")


def audit_log_path(output_dir: str) -> str:
    return os.path.join(output_dir, "admin_audit.log")


def write_audit(output_dir: str, action: str, detail: str) -> None:
    """Append an entry to the audit log. Best-effort — never raises."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now(TZ).isoformat()
        with open(audit_log_path(output_dir), "a") as f:
            f.write(f"{ts} | {action} | {detail}\n")
    except OSError:
        pass  # Audit logging is best-effort


def read_audit(output_dir: str, limit: int = 50) -> list[str]:
    """Return the last `limit` audit entries, newest last."""
    path = audit_log_path(output_dir)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.readlines()
    return [l.rstrip() for l in lines[-limit:]]

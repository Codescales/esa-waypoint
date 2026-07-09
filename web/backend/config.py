import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPREADSHEET = str(ROOT / "output" / "incentive_plan.xlsx")
DEFAULT_BRIEFS_DIR = str(ROOT / "output" / "briefs")
DEFAULT_DB_PATH = str(ROOT / "output" / "esa.db")

SPREADSHEET_PATH = os.environ.get("SPREADSHEET_PATH", DEFAULT_SPREADSHEET)
BRIEFS_DIR = os.environ.get("BRIEFS_DIR", DEFAULT_BRIEFS_DIR)
DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
REPO_TYPE = os.environ.get("REPO_TYPE", "sqlite")  # "sqlite" | "xlsx"
SHARED_PASSWORD = os.environ.get("SHARED_PASSWORD", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-change-in-prod")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://localhost:3000")
SESSION_MAX_AGE = 60 * 60 * 24  # 24 hours
ADMIN_SESSION_MAX_AGE = 60 * 60  # 1 hour
SNAPSHOT_KEEP = int(os.environ.get("SNAPSHOT_KEEP", "10"))
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").lower() == "true"


def validate() -> None:
    """Validate required config at startup. Raises ValueError on misconfiguration."""
    missing = []
    if not SHARED_PASSWORD:
        missing.append("SHARED_PASSWORD")
    if not ADMIN_PASSWORD:
        missing.append("ADMIN_PASSWORD")
    if not SESSION_SECRET or SESSION_SECRET in ("dev-secret-change-in-prod", "change-me-in-production"):
        missing.append("SESSION_SECRET (must not be default/weak value)")
    if missing:
        raise ValueError(
            f"Required environment variables missing or weak: {', '.join(missing)}. "
            "Set them in .env or pass as environment variables."
        )

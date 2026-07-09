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

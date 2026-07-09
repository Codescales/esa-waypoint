"""ESA Incentive Pipeline - main orchestrator.

Usage:
    python -m src.pipeline [--horaro-org ORG] [--horaro-schedules SLUGS]
                           [--oengus-marathon ID] [--output PATH]
                           [--format xlsx|csv]

    # Push approved incentives from the spreadsheet to Tiltify
    python -m src.pipeline --tiltify-push --tiltify-campaign-id <uuid>

    # List what would be created without touching Tiltify
    python -m src.pipeline --tiltify-dry-run --tiltify-campaign-id <uuid>

    # Interactive login → output/tiltify_session.json
    python -m src.pipeline --tiltify-login

Environment variables (fallback):
    HORARO_ORG, HORARO_SCHEDULES, OENGUS_MARATHON_ID, OUTPUT_FILE, OUTPUT_FORMAT
    TILTIFY_CAMPAIGN_ID, TILTIFY_COOKIE, TILTIFY_SESSION_PATH,
    TILTIFY_HEADLESS, INCENTIVE_DOLLAR_PER_MIN
"""

import argparse
import os
import sys
from datetime import datetime

from .horaro import fetch_schedule, ScheduleItem
from .oengus import fetch_marathon, set_auth_token, set_session_cookie, login, refresh_token, MfaRequired, _clear_session, OengusMarathon
from .spreadsheet import generate_spreadsheet


def _load_dotenv():
    """Load .env file into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def run_pipeline(
    horaro_org: str = "",
    horaro_schedules: str = "",
    oengus_marathon_id: str = "",
    oengus_token: str = "",
    output_path: str = "",
    output_format: str = "xlsx",
) -> dict:
    """Run the full pipeline: pull Horaro + Oengus, write spreadsheet.

    Returns a summary dict with counts of runs/incentives pulled.
    Reads env vars as defaults for any empty parameter.
    """
    _load_dotenv()

    horaro_org = horaro_org or os.getenv("HORARO_ORG", "esa")
    horaro_schedules = horaro_schedules or os.getenv("HORARO_SCHEDULES", "")
    oengus_marathon_id = oengus_marathon_id or os.getenv("OENGUS_MARATHON_ID", "")
    oengus_token = oengus_token or os.getenv("OENGUS_TOKEN", "")
    output_path = output_path or os.getenv("OUTPUT_FILE", "output/incentive_plan.xlsx")
    output_format = output_format or os.getenv("OUTPUT_FORMAT", "xlsx")

    if not horaro_schedules:
        raise ValueError("No Horaro schedules specified. Set HORARO_SCHEDULES env var or pass horaro_schedules.")
    if not oengus_marathon_id:
        raise ValueError("No Oengus marathon ID specified. Set OENGUS_MARATHON_ID env var or pass oengus_marathon_id.")

    if oengus_token:
        set_auth_token(oengus_token)

    schedule_slugs = [s.strip() for s in horaro_schedules.split(",") if s.strip()]

    all_items: list[ScheduleItem] = []
    for slug in schedule_slugs:
        schedule = fetch_schedule(horaro_org, slug)
        all_items.extend(schedule.items)

    all_items.sort(key=lambda x: x.scheduled)
    marathon = fetch_marathon(oengus_marathon_id)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if output_format == "xlsx":
        _, orphaned = generate_spreadsheet(all_items, marathon, output_path)
    else:
        _write_csv(all_items, marathon, output_path)

    return {
        "runs": len(all_items),
        "incentives": len(marathon.submissions),
        "output_path": output_path,
        "format": output_format,
    }


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(
        description="ESA Incentive Pipeline: Horaro schedule + Oengus submissions -> spreadsheet"
    )
    parser.add_argument("--horaro-org", default=os.getenv("HORARO_ORG", "esa"),
                        help="Horaro organization slug")
    parser.add_argument("--horaro-schedules", default=os.getenv("HORARO_SCHEDULES", ""),
                        help="Comma-separated schedule slugs")
    parser.add_argument("--oengus-marathon", default=os.getenv("OENGUS_MARATHON_ID", ""),
                        help="Oengus marathon ID")
    parser.add_argument("--oengus-token", default=os.getenv("OENGUS_TOKEN", ""),
                        help="Oengus Bearer token for authenticated access (JWT from Authorization header)")
    parser.add_argument("--oengus-refresh", action="store_true",
                        help="Refresh the Oengus token before running (extends expiry by 7 days)")
    parser.add_argument("--oengus-username", default=os.getenv("OENGUS_USERNAME", ""),
                        help="Oengus username for auto-login (used with --oengus-password)")
    parser.add_argument("--oengus-password", default=os.getenv("OENGUS_PASSWORD", ""),
                        help="Oengus password for auto-login (used with --oengus-username)")
    parser.add_argument("--oengus-cookie", default=os.getenv("OENGUS_COOKIE", ""),
                        help="Oengus session cookie for authenticated access (moderator)")
    parser.add_argument("--output", default=os.getenv("OUTPUT_FILE", "output/incentive_plan.xlsx"),
                        help="Output file path")
    parser.add_argument("--format", default=os.getenv("OUTPUT_FORMAT", "xlsx"),
                        choices=["xlsx", "csv"], help="Output format")

    _add_tiltify_args(parser)
    args = parser.parse_args()

    if args.tiltify_login:
        return _tiltify_login_main(args)
    if args.tiltify_push or args.tiltify_dry_run:
        return _tiltify_push_main(args)

    if not args.horaro_schedules:
        print("ERROR: No Horaro schedules specified. Use --horaro-schedules or HORARO_SCHEDULES env var.")
        sys.exit(1)
    if not args.oengus_marathon:
        print("ERROR: No Oengus marathon ID specified. Use --oengus-marathon or OENGUS_MARATHON_ID env var.")
        sys.exit(1)

    if args.oengus_token:
        set_auth_token(args.oengus_token)
        print("Using Oengus Bearer token for authenticated access.")
        if args.oengus_refresh:
            print("  Refreshing token ...")
            try:
                new_token = refresh_token()
                print("  Token refreshed (extended by 7 days).")
                _save_token_to_env(new_token)
            except ValueError as e:
                print(f"  WARNING: Token refresh failed: {e}")
                print("  Token may be expired. Incentive data will be unavailable.")
                print("  To fix: obtain a fresh token from browser DevTools > Network > Authorization header")
                print("  and update OENGUS_TOKEN in .env, or use --oengus-username/--oengus-password.")
                print("  Continuing without authenticated access.")
                _clear_session()
    elif args.oengus_username and args.oengus_password:
        print(f"  Logging into Oengus as {args.oengus_username} ...")
        try:
            token = login(args.oengus_username, args.oengus_password)
            print(f"  Login successful, token obtained.")
        except MfaRequired:
            code = input("  2FA code required: ").strip()
            if not code:
                print("  ERROR: 2FA code is required for this account.")
                sys.exit(1)
            try:
                token = login(args.oengus_username, args.oengus_password, two_factor_code=code)
                print(f"  Login successful, token obtained.")
            except ValueError as e:
                print(f"  ERROR: {e}")
                sys.exit(1)
        except ValueError as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
    elif args.oengus_cookie:
        set_session_cookie(args.oengus_cookie)
        print("Using Oengus session cookie for authenticated access.")

    schedule_slugs = [s.strip() for s in args.horaro_schedules.split(",") if s.strip()]

    print(f"Horaro org: {args.horaro_org}")
    print(f"Horaro schedules: {schedule_slugs}")
    print(f"Oengus marathon: {args.oengus_marathon}")
    print(f"Output: {args.output}")

    all_items: list[ScheduleItem] = []
    for slug in schedule_slugs:
        print(f"  Fetching schedule: {slug} ...")
        schedule = fetch_schedule(args.horaro_org, slug)
        all_items.extend(schedule.items)
        print(f"    -> {len(schedule.items)} items from '{schedule.name}'")

    all_items.sort(key=lambda x: x.scheduled)
    print(f"  Total schedule items: {len(all_items)}")

    print(f"  Fetching Oengus marathon: {args.oengus_marathon} ...")
    marathon = fetch_marathon(args.oengus_marathon)
    print(f"    -> {marathon.name}, {len(marathon.submissions)} submissions")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    if args.format == "xlsx":
        _, orphaned = generate_spreadsheet(all_items, marathon, args.output)
        print(f"  Spreadsheet written to: {args.output}")
        if orphaned:
            print(f"  WARNING: {len(orphaned)} annotated runs were removed from the schedule:")
            for key in sorted(orphaned):
                print(f"    - {key}")
            print(f"  Annotations for these runs have been lost. Review the new sheet.")
    else:
        _write_csv(all_items, marathon, args.output)
        print(f"  CSV written to: {args.output}")

    print("Done.")


def _save_token_to_env(token: str) -> None:
    """Update OENGUS_TOKEN in the .env file so agents pick up the refreshed token."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r") as f:
        lines = f.readlines()
    updated = False
    with open(env_path, "w") as f:
        for line in lines:
            if line.startswith("OENGUS_TOKEN="):
                f.write(f"OENGUS_TOKEN={token}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"OENGUS_TOKEN={token}\n")
    os.chmod(env_path, 0o600)
    print("  Updated OENGUS_TOKEN in .env")


def _write_csv(items: list[ScheduleItem], marathon: OengusMarathon, path: str):
    import csv
    from .spreadsheet import _build_cross_reference

    xref = _build_cross_reference(items, marathon.submissions)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scheduled", "Game", "Category", "Estimate", "Platform",
            "Players", "Runner", "Twitch", "Discord", "Twitter",
            "Note", "Layout", "Stream", "Submission ID", "Category ID",
            "Incentives", "Commentator", "Upload Speed", "Pronouns",
            "Show Cam", "Runner Comments",
        ])
        for xr in xref:
            writer.writerow([
                xr.scheduled.isoformat(), xr.game, xr.category, xr.estimate,
                xr.platform, xr.players, xr.runner_display, xr.runner_twitch,
                xr.runner_discord, xr.runner_twitter, xr.note, xr.layout,
                xr.stream, xr.submission_id, xr.category_id,
                xr.incentives, xr.commentator, xr.upload_speed,
                xr.pronouns, xr.show_cam, xr.runner_comments,
            ])


def _add_tiltify_args(parser: argparse.ArgumentParser) -> None:
    tireward = parser.add_argument_group("tiltify", "Push approved incentives to Tiltify via browser automation")
    tireward.add_argument("--tiltify-push", action="store_true",
                          help="Push approved incentive rows to Tiltify (requires TILTIFY_CAMPAIGN_ID)")
    tireward.add_argument("--tiltify-dry-run", action="store_true",
                          help="List the incentives that would be pushed; do not contact Tiltify")
    tireward.add_argument("--tiltify-login", action="store_true",
                          help="Open a browser, log into Tiltify, persist session to output/tiltify_session.json")
    tireward.add_argument("--tiltify-campaign-id", default=os.getenv("TILTIFY_CAMPAIGN_ID", ""),
                          help="Tiltify campaign UUID (from dashboard URL or DevTools)")
    tireward.add_argument("--tiltify-session", default=os.getenv("TILTIFY_SESSION_PATH", "output/tiltify_session.json"),
                          help="Path to a Playwright storage_state JSON")
    tireward.add_argument("--tiltify-cookie", default=os.getenv("TILTIFY_COOKIE", ""),
                          help="Raw Cookie header (fallback when no session file)")
    tireward.add_argument("--tiltify-headless", default=os.getenv("TILTIFY_HEADLESS", "true"),
                          choices=["true", "false"], help="Headless browser mode (set false to debug)")
    tireward.add_argument("--tiltify-keep-going", action="store_true",
                          help="Continue past per-row errors during push")
    tireward.add_argument("--tiltify-max", type=int, default=0,
                          help="Stop after N creates (0 = unlimited)")
    tireward.add_argument("--incentive-dollar-per-minute", type=float,
                          default=float(os.getenv("INCENTIVE_DOLLAR_PER_MIN", "5")),
                          help="Dollars per minute to compute reward/target amount (default 5)")
    tireward.add_argument("--source", default="xlsx", choices=["xlsx", "db"],
                          help="Source of incentive data: xlsx (default) or db")
    tireward.add_argument("--db-path", default=os.getenv("DB_PATH", "output/esa.db"),
                          help="SQLite DB path (default: DB_PATH env or output/esa.db)")


def _tiltify_push_main(args) -> int:
    """Execute the spreadsheet → Tiltify push.

    Reads incentives from --output (default output/incentive_plan.xlsx)
    and pushes every row with status=Approved and valid_for_game in
    {Yes, Needs Review}. Idempotent against existing Tiltify rewards
    by (name, amount) match.
    """
    from .tiltify import (
        TiltifySession, PlaywrightTiltifyClient, TiltifySessionError,
    )
    from .tiltify_push import (
        collect_actions, execute, summarize, format_action_line, format_summary_line,
    )
    from .xlsx_reader import read_incentives, read_incentives_from_db

    if args.source == "db":
        db_path = args.db_path or os.getenv("DB_PATH", "output/esa.db")
        if not os.path.exists(db_path):
            print(f"ERROR: DB not found at {db_path}. Run admin refresh first.")
            return 1
        print(f"Reading incentives from DB {db_path} ...")
        rows = read_incentives_from_db(db_path)
    else:
        spreadsheet = args.output
        if not os.path.exists(spreadsheet):
            print(f"ERROR: spreadsheet not found at {spreadsheet}. Run the pipeline first.")
            return 1
        print(f"Reading incentives from {spreadsheet} ...")
        rows = read_incentives(spreadsheet)
    print(f"  Read {len(rows)} incentive rows.")

    existing_rewards = []
    client = None
    if not args.tiltify_dry_run:
        session = _load_tiltify_session(args)
        if session is None:
            print("ERROR: no Tiltify session. Run --tiltify-login first.")
            return 1
        headless = (args.tiltify_headless == "true")
        client = PlaywrightTiltifyClient(
            session=session,
            campaign_id=args.tiltify_campaign_id,
            headless=headless,
        )
        try:
            client.open()
            print("Listing existing Tiltify rewards ...")
            existing_rewards = client.list_rewards()
            print(f"  Found {len(existing_rewards)} existing rewards.")
        except Exception as e:
            print(f"ERROR listing existing rewards: {e}")
            client.close()
            return 1
    else:
        print("--tiltify-dry-run: skipping session/client (no Tiltify contact)")

    print()
    actions = collect_actions(rows, existing_rewards, dollar_per_minute=args.incentive_dollar_per_minute)
    for a in actions:
        print(format_action_line(a))
    print()

    pre_summary = summarize(actions)
    print(format_summary_line(pre_summary))
    print()

    if args.tiltify_dry_run:
        print("Dry run complete. Re-run with --tiltify-push to apply.")
        return 0

    would_create = [a for a in actions if a.status == "would-create"]
    if not would_create:
        print("Nothing to create — exiting.")
        if client:
            client.close()
        return 0

    if args.tiltify_max > 0:
        for a in would_create[args.tiltify_max:]:
            a.status = "skip"
            a.reason = f"skipped by --tiltify-max {args.tiltify_max}"

    print(f"Pushing {min(len(would_create), args.tiltify_max or len(would_create))} incentives ...")
    try:
        summary = execute(actions, client, dry_run=False, keep_going=args.tiltify_keep_going)
    finally:
        if client:
            client.close()

    print()
    print(format_summary_line(summary))
    if summary.failed:
        print()
        print(f"{summary.failed} rows failed. Re-run --tiltify-push after fixing the issues; the")
        print("already-created rewards will be skipped on the next run via the idempotency check.")
    return summary.exit_code


def _tiltify_login_main(args) -> int:
    """Open a visible browser, let the user log in to Tiltify, persist the
    resulting session to output/tiltify_session.json.
    """
    from .tiltify import save_session_from_console_cookies

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"ERROR: Playwright not installed. Install with: pip install playwright && playwright install chromium ({e})")
        return 1

    session_path = args.tiltify_session
    os.makedirs(os.path.dirname(session_path) or ".", exist_ok=True)

    print(f"Opening browser for interactive Tiltify login ...")
    print(f"  1) Sign in to https://app.tiltify.com/login")
    print(f"  2) After the dashboard loads, return to this terminal and press Enter.")
    print(f"  3) The session will be written to {session_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://app.tiltify.com/login", wait_until="domcontentloaded")
        try:
            input("Press Enter once you are logged in and the dashboard is visible > ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 1
        cookies = context.cookies("https://app.tiltify.com/")
        save_session_from_console_cookies(session_path, {"cookies": cookies, "origins": []})
        names = [c["name"] for c in cookies]
        print(f"Saved {len(cookies)} cookies: {names}")
        print(f"Storage state written to: {session_path}  (chmod 600)")
        browser.close()
    return 0


def _load_tiltify_session(args):
    from .tiltify import TiltifySession, TiltifySessionError
    session_paths = [args.tiltify_session]
    for p in session_paths:
        if not p or not os.path.exists(p):
            continue
        try:
            return TiltifySession.from_storage_state(p)
        except TiltifySessionError as e:
            print(f"  Warning: session at {p} rejected: {e}")
            break
    if args.tiltify_cookie:
        try:
            return TiltifySession.from_cookie_header(args.tiltify_cookie)
        except TiltifySessionError as e:
            print(f"  Warning: --tiltify-cookie rejected: {e}")
    return None


if __name__ == "__main__":
    sys.exit(main() or 0)

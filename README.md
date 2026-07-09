# ESA Incentive Pipeline

Pulls ESA schedule data from Horaro.net and accepted run submissions from Oengus.io, cross-references them, and generates an incentive planning spreadsheet for the fundraising team.

## Quick Start

```bash
# Install uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies and activate venv
uv sync
source .venv/bin/activate

# Copy and configure environment
cp .env.example .env
# Edit .env with your Oengus token (from browser DevTools > Network > Authorization header)

# Run
uv run python -m src.pipeline --oengus-refresh
```

Output: `output/incentive_plan.xlsx`

## How It Works

```
Horaro API v1 ──→ Schedule items (game, category, estimate, players, time)
                          │
                          ├── Cross-reference by submission_id
                          │
Oengus API ────→ Submissions (runner info, incentive text, contact details)
                          │
                          ▼
              Incentives Detail sheet (auto-split, categorized, reviewed)
                          │
                          ▼
              Fundraising View sheet (live formulas, per-run summary)
```

## Spreadsheet Sheets

| Sheet | Purpose |
|-------|---------|
| **Schedule** | All 176 runs from Horaro (reference) |
| **Submissions** | All 186 Oengus submissions (reference) |
| **Cross-Reference** | Matched data. Missing incentives highlighted red |
| **Incentives Detail** | Individual incentives with review workflow |
| **Fundraising View** | Per-run summary with live formulas + team annotations |
| **Marathon Info** | Summary statistics |

## Incentive Review Workflow

The **Incentives Detail** sheet is the primary working sheet:

1. Incentive text is auto-split into individual rows
2. Time estimates are auto-extracted from text
3. Status is auto-guessed: To-Do → In Review → Approved
4. Team reviews each incentive:
   - **Incentive Category**: Reward / Poll-Bid War / Target (dropdown)
   - **Valid for Game**: Yes / No / Needs Review (dropdown)
   - **Incentive Estimate**: Minutes (auto-extracted, editable)
   - **Status**: To-Do / In Review / Needs Information / Approved / Removed (dropdown)
5. Fundraising View updates live via Excel formulas

### Status Flow

```
To-Do ──→ In Review ──→ Approved (manual only)
  │           │
  └──→ Needs Information ←── (invalid game, unknown estimate)
```

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `HORARO_ORG` | `esa` | Horaro organization slug |
| `HORARO_SCHEDULES` | `2026-summer1,2026-summer2` | Comma-separated schedule slugs |
| `OENGUS_MARATHON_ID` | `ESA-Sum26` | Oengus marathon ID |
| `OENGUS_TOKEN` | (required) | Bearer token for moderator access |
| `OUTPUT_FILE` | `output/incentive_plan.xlsx` | Output path |
| `OUTPUT_FORMAT` | `xlsx` | `xlsx` or `csv` |

## CLI Flags

```
python3 -m src.pipeline [options]

  --horaro-org ORG           Horaro organization (default: esa)
  --horaro-schedules SLUGS   Comma-separated schedule slugs
  --oengus-marathon ID       Oengus marathon ID
  --oengus-token TOKEN       Bearer token (or set OENGUS_TOKEN in .env)
  --oengus-refresh           Refresh token before run (extends 7 days)
  --oengus-username USER     Username for password login (fallback)
  --oengus-password PASS     Password for login (fallback)
  --oengus-cookie COOKIE     Session cookie (fallback)
  --output PATH              Output file path
  --format xlsx|csv          Output format
```

## Auth

Incentive data requires Oengus moderator access. The pipeline uses a Bearer token:

1. Log into oengus.io in your browser
2. Open DevTools (F12) → Network tab
3. Find any API request to `oengus.io`
4. Copy the `Authorization: Bearer eyJ...` header value
5. Set `OENGUS_TOKEN=eyJ...` in `.env`

The token is auto-refreshed on each run (`--oengus-refresh`), extending expiry by 7 days. The refreshed token is written back to `.env`.

## Re-running

The pipeline is designed to be re-run when the schedule changes. On re-run:

- **Incentives Detail**: Manual edits preserved by hidden UUID column. New incentives get fresh UUIDs. Removed incentives marked "Removed".
- **Fundraising View**: Formulas regenerate fresh. Annotation columns (Priority, Contact Status, Assigned To, Notes) preserved by game+category key.
- Orphaned annotations (runs removed from schedule) are warned.

## Pushing Approved Incentives to Tiltify

Tiltify's V5 API exposes **no write endpoints** for rewards, polls, or targets
(see ADR-012). The `--tiltify-*` flags therefore drive the Tiltify dashboard
via Playwright browser automation. The push is **idempotent**: an existing
Tiltify reward with the same `(name, amount)` (within 100 cents) is skipped.

### One-time set-up

```bash
uv run python -m playwright install chromium
```

### Login once to capture a session

```bash
python3 -m src.pipeline --tiltify-login
# → a Chrome window opens at https://app.tiltify.com/login
# → log in normally (handles 2FA, social logins, anything the browser lets you do)
# → after the dashboard loads, return to the terminal and press Enter
# → output/tiltify_session.json gets written (chmod 600, gitignored)
```

Re-run `--tiltify-login` whenever the Tiltify session expires.

### Dry-run first

```bash
python3 -m src.pipeline --tiltify-dry-run \
    --tiltify-campaign-id <campaign-uuid>
```

Reads `output/incentive_plan.xlsx`, classifies every row whose
`Status=Approved` and `Valid for Game ∈ {Yes, Needs Review}`, computes
the donation amount (`incentive_estimate` × `INCENTIVE_DOLLAR_PER_MIN`,
default $5/min), and prints `[W] reward/poll/target …` lines without
contacting Tiltify. Status legend: `W` would-create, `S` skip,
`N` needs-info, `C` created (only after a real push), `F` failed.

### Push for real (small batch first)

```bash
# Watch the clicks the first time
python3 -m src.pipeline --tiltify-push \
    --tiltify-campaign-id <uuid> \
    --tiltify-headless=false \
    --tiltify-max 1

# Then a full run, surviving per-row errors
python3 -m src.pipeline --tiltify-push \
    --tiltify-campaign-id <uuid> \
    --tiltify-keep-going
```

The campaign UUID is in the dashboard URL:
`https://app.tiltify.com/@<user>/<campaign-slug>` — open "Setup >
Information" and copy the Campaign ID shown there.

### Spreadsheet → Tiltify mapping

| Spreadsheet column | Tiltify field     | Notes |
|--------------------|-------------------|-------|
| Incentive text first line       | `name`             | Short title in the dashboard list |
| Incentive text rest of lines    | `description`      | Prefixed with `[{runner} · {game}]` for traceability |
| `incentive_category=Reward`    | reward create      | `amount = incent_estimate_min × $/min` |
| `incentive_category=Poll-Bid War` | poll create      | Options = lines after the first line |
| `incentive_category=Target`     | target create      | `amount = incent_estimate_min × $/min` |
| `incentive_estimate` empty      | (skipped)         | Marked `needs-info` — Tiltify rejects $0 rewards |
| Tiltify reward with matching `(name, amount)` | (skipped) | Idempotent on re-run |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TILTIFY_CAMPAIGN_ID` | (required for push) | Tiltify campaign UUID |
| `TILTIFY_SESSION_PATH` | `output/tiltify_session.json` | Playwright storage_state path |
| `TILTIFY_COOKIE` | (fallback) | Raw `Cookie:` header when no session file |
| `TILTIFY_HEADLESS` | `true` | `false` for debugging |
| `INCENTIVE_DOLLAR_PER_MIN` | `5` | Reward/target amount per estimate minute |

## Architecture

```
src/
├── horaro.py           Horaro API v1 client
├── oengus.py           Oengus API client (public + authenticated)
├── incentives.py       Incentive text parsing, splitting, validation
├── spreadsheet.py      XLSX generation (6 sheets, formulas, dropdowns)
├── pipeline.py         CLI orchestrator, .env loading, auth flow + tiltify push
├── find_incentives.py  GDQ tracker search for incentive ideas
├── src_api.py          Speedrun.com API client (shared canonical helpers)
├── xlsx_reader.py      Spreadsheet reader — load + filter runs/incentives
├── slugs.py            Slug generation for run briefs (stream, time, game)
├── brief.py            CLI subcommands for host brief generation
├── tiltify.py          TiltifySession + PlaywrightTiltifyClient (dashboard automation)
├── tiltify_push.py     Pure-Python classifier + idempotency (no browser)
└── __init__.py

web/
├── backend/
│   ├── app.py          FastAPI application entry point
│   ├── config.py       Environment variable config
│   ├── auth.py         Shared-password cookie session auth
│   ├── deps.py         FastAPI dependency injection
│   ├── repo.py         IncentiveRepo protocol + XlsxIncentiveRepo
│   ├── models.py       Pydantic DTOs matching xlsx_reader dataclasses
│   ├── markdown_render.py  Markdown→HTML rendering
│   └── routes/         REST API route modules
└── frontend/           Next.js App Router (TypeScript + Tailwind CSS)

tests/
├── test_slugs.py           Unit tests for slug generation
├── test_xlsx_reader.py     Unit tests for spreadsheet reading + filtering
├── test_tiltify_push.py    Unit tests for Tiltify classifier + idempotency
└── fixtures/
    └── brief_test.xlsx     Synthetic test fixture (8 runs, edge cases)

docs/
└── adr/             Architecture Decision Records

.opencode/skills/
├── incentive-pipeline/
│   └── SKILL.md     Agent skill: generate incentive planning spreadsheet
├── find-incentives/
│   └── SKILL.md     Agent skill: research incentive ideas for a game
└── brief/
    ├── SKILL.md     Agent skill: generate host briefs for any run, shift, or
    │                      the full marathon
    └── TEMPLATES.md Example brief shapes for scan/interview/full/batch modes
```

## Finding Incentive Ideas

The `/find-incentives` skill helps the fundraising team research incentive ideas for games that don't have any yet. It searches the GDQ donation tracker for similar games and returns categorized suggestions.

```
/find-incentives "Super Mario Bros"
```

Output:
```json
{
  "game": "Super Mario Bros",
  "incentives": [
    {
      "name": "Character Choice",
      "run": "Super Mario Bros",
      "description": "Choose which character to use...",
      "category": "Poll-Bid War",
      "event": "sgdq2025",
      "source_url": "https://tracker.gamesdonequick.com/tracker/bid/..."
    }
  ]
}
```

Categories: **Poll-Bid War** (choice/pick-style), **Target** (if-met donation goals), **Reward** (always-active incentives).

## Generating Host Briefs

The `/brief` skill generates scanning/interview/full-depth briefs for
marathon hosts. It reads `output/incentive_plan.xlsx` (generated by
the pipeline) and fetches category/WR data from speedrun.com, with
Wikipedia/websearch for studio context. See `.opencode/skills/brief/SKILL.md`.

Triggers:

| Command | What it does |
|---------|-------------|
| `/brief` | Interactive picker → scan brief for selected run |
| `/brief interview <pick>` | Interview-focused brief (expanded context, no fabricated questions) |
| `/brief full <pick>` | All sections at full depth |
| `/brief shift <start>-<end> [--stream N]` | Batch briefs for a time window with `_index.md` overview |
| `/brief next Nh [--stream N]` | Batch: next N hours |
| `/brief marathon [--stream N]` | Full-marathon briefs |

Output: `output/briefs/<slug>.md` + `output/briefs/<slug>.json` (sidecar).

## Web Viewer

The `web/` directory contains a browser-based host viewer that reads the
same `output/incentive_plan.xlsx` and `output/briefs/*.md` files and
renders them for mobile/desktop browsers.

```
web/
├── backend/        FastAPI (Python) — REST API reusing src/xlsx_reader
└── frontend/       Next.js App Router (TypeScript + Tailwind) — host UI
```

### Quick Start (development)

```bash
# 1. Generate the spreadsheet if not done already
python3 -m src.pipeline

# 2. Start the backend (terminal 1)
SHARED_PASSWORD=devpass SESSION_SECRET=dev-secret \
  python3 -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload

# 3. Start the frontend (terminal 2)
cd web/frontend
npm install
npm run dev         # → http://localhost:3000

# 4. Open http://localhost:3000/login → password: devpass
```

### Production (Docker Compose)

```bash
export SHARED_PASSWORD=<strong-password>
export SESSION_SECRET=<random-secret>
docker compose up --build -d
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000  (proxy routes /api/* to backend)
```

Environment variables for the backend container:

| Variable | Default | Description |
|----------|---------|-------------|
| `SPREADSHEET_PATH` | `output/incentive_plan.xlsx` | Path to the XLSX |
| `BRIEFS_DIR` | `output/briefs` | Path to brief markdown files |
| `SHARED_PASSWORD` | (required) | Single password for all hosts |
| `SESSION_SECRET` | `dev-secret` | Key for signing session cookies |
| `CORS_ORIGIN` | `http://localhost:3000` | Allowed frontend origin |

### Pages

| Route | Description |
|-------|-------------|
| `/` | Marathon view — stream tabs + day cards |
| `/schedule` | Full schedule table, searchable, filterable |
| `/incentives` | Read-only incentive table, filter by status/category |
| `/run/[slug]` | Run brief detail with structured sidecar sections |
| `/login` | Shared-password login |

### Brief sidecars

When the brief agent passes `--data '$JSON'` to `python3 -m src.brief write`,
the structured data is saved as `output/briefs/<slug>.json` alongside the
markdown. The web viewer uses this for structured sections (incentive cards,
runner portfolio, sibling runs, sources). Without the sidecar, the page
shows only rendered markdown prose.

See `.opencode/skills/brief/SKILL.md` step 4 for the sidecar schema.

## Architecture Decisions

See `docs/adr/` for key decisions:
- `008-host-brief-skill.md` — Brief generation skill
- `009-web-viewer-architecture.md` — FastAPI + Next.js two-tier design
- `010-shared-password-auth.md` — Cookie-based shared auth model
- `011-repository-seam-for-incentives.md` — Protocol for XLSX→SQLite migration
- `012-tiltify-push-via-browser-automation.md` — Why we use Playwright to push incentives to Tiltify (no write API)
- `012-horaro-parity-check.md` — xlsx vs live Horaro schedule comparison

## Phase 2: SQLite-Backed Data Layer

The web viewer is backed by `output/esa.db` (SQLite, WAL mode) instead
of the xlsx directly. The xlsx remains the upstream source — it's
imported into the DB on every admin refresh.

### First-time setup

```bash
# 1. Generate the spreadsheet
python3 -m src.pipeline

# 2. Import into SQLite (creates output/esa.db)
python3 -m src.import_to_sqlite
# Or with --dry-run to preview what would change

# 3. Start the web viewer
docker compose up -d
```

### Admin operations

Visit `http://<host>:3001/admin` (admin password from `.env`).

- **Refresh** — Re-import the xlsx into the DB. A snapshot of the current
  DB is taken first, so any bad import can be rolled back.
- **Restore** — Roll back to a previous snapshot.
- **Snapshots** — List of all available snapshots with size and age.
- **Status** — DB size, schema version, row counts, last import time.
- **Audit log** — Recent admin actions (login, refresh, restore, host CRUD).
- **Hosts** — Manage the host identity list (Phase 2.4; OIDC later).

### Phase 2 endpoints (all behind shared password)

```
GET    /api/runs?stream=&window=&next_hours=&marathon=
GET    /api/runs/{slug}
GET    /api/incentives?run_slug=&status=&category=&stream=
GET    /api/incentives/{uuid}
PATCH  /api/incentives/{uuid}         # category / valid / status / estimate
GET    /api/notes?run_slug=...        # list notes
POST   /api/notes                     # create (attributed to active host)
PATCH  /api/notes/{id}                # edit (own notes or admin)
DELETE /api/notes/{id}                # delete (own notes or admin)
GET    /api/notes/active-host         # current attribution target
```

### Phase 2 admin endpoints (separate password)

```
POST   /api/admin/login
POST   /api/admin/logout
GET    /api/admin/status
POST   /api/admin/refresh
GET    /api/admin/snapshots
POST   /api/admin/restore
GET    /api/admin/audit
GET    /api/admin/hosts
POST   /api/admin/hosts               # add or reactivate
DELETE /api/admin/hosts/{id}         # soft-delete (is_active=false)
```

## Tests

The project has a test suite covering pure modules, the SQLite data
layer, snapshots, the import pipeline, the SQLite repo, and the
admin/notes API endpoints:

```bash
# Install dev extras (first time)
uv sync --extra dev

# Run all tests
uv run python -m pytest tests/ -v
```

Current coverage (118 tests):
- `test_slugs.py` — slug generation edge cases
- `test_xlsx_reader.py` — xlsx reading and filtering
- `test_db.py` — DB init, schema, WAL, FK, schema_version, host seeding
- `test_snapshot.py` — create/list/restore/prune, malformed timestamp skipping
- `test_import_to_sqlite.py` — round-trip, edit preservation, dry-run
- `test_repo_sqlite.py` — Protocol conformance, parity with xlsx repo
- `test_admin_api.py` — auth, refresh, restore, hosts, audit
- `test_notes_api.py` — CRUD, authz, validation, size limits

The fixture `tests/fixtures/brief_test.xlsx` (4 runs, 2 incentives)
is committed.

## API Safety

All Horaro and Oengus API calls are **GET (read-only)**. The login/refresh POSTs are authentication only. No data is ever modified on Horaro or Oengus.

## Documentation

- `docs/adr/` — Architecture Decision Records explaining key design choices
- `.opencode/skills/incentive-pipeline/SKILL.md` — Agent skill for `/incentive-pipeline`
- `.opencode/skills/brief/SKILL.md` — Agent skill for `/brief` host briefs
- `https://github.com/BongoEADGC6/esa-incentive-pipeline` — Source repository

#!/usr/bin/env bash
# dev.sh — start backend + frontend for local testing
# Usage: ./dev.sh
# Optionally override passwords via env:
#   SHARED_PASSWORD=x ADMIN_PASSWORD=y SESSION_SECRET=z ./dev.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Credentials ────────────────────────────────────────────────────────────
# Defaults are dev-only values. Override via env or edit here.
SHARED_PASSWORD="${SHARED_PASSWORD:-devpass}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-adminpass}"
SESSION_SECRET="${SESSION_SECRET:-dev-local-secret-change-me}"
CORS_ORIGIN="${CORS_ORIGIN:-http://localhost:3001}"
SECURE_COOKIES="${SECURE_COOKIES:-false}"
REPO_TYPE="${REPO_TYPE:-sqlite}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

# ── Helpers ─────────────────────────────────────────────────────────────────
# Launch a process fully detached (double-fork) so it survives shell exit.
# Usage: detach <pidfile> <logfile> [env key=val ...] -- <cmd> [args...]
detach() {
  local pidfile="$1"; shift
  local logfile="$1"; shift
  local env_args=()
  while [[ "$1" != "--" ]]; do
    env_args+=("$1"); shift
  done
  shift  # consume "--"

  python3 - "$pidfile" "$logfile" "${env_args[@]}" -- "$@" <<'PYEOF'
import os, sys, subprocess

args = sys.argv[1:]
sep = args.index("--")
meta = args[:sep]
cmd  = args[sep+1:]

pidfile = meta[0]
logfile = meta[1]
env_pairs = meta[2:]

env = os.environ.copy()
for pair in env_pairs:
    k, v = pair.split("=", 1)
    env[k] = v

# Double-fork to fully detach
if os.fork() > 0:
    sys.exit(0)
os.setsid()
if os.fork() > 0:
    sys.exit(0)

with open(logfile, "a") as f:
    p = subprocess.Popen(cmd, env=env, stdout=f, stderr=f)
    with open(pidfile, "w") as pf:
        pf.write(str(p.pid) + "\n")
    p.wait()
PYEOF
}

kill_pid_file() {
  local pidfile="$1"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    kill "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
}

BACKEND_PID_FILE="/tmp/esa-backend.pid"
FRONTEND_PID_FILE="/tmp/esa-frontend.pid"

# ── Stop any running instances ───────────────────────────────────────────────
kill_pid_file "$BACKEND_PID_FILE"
kill_pid_file "$FRONTEND_PID_FILE"
sleep 1

# ── Backend ─────────────────────────────────────────────────────────────────
echo "Starting backend on port ${BACKEND_PORT}..."
> /tmp/esa-backend.log
detach "$BACKEND_PID_FILE" /tmp/esa-backend.log \
  "SHARED_PASSWORD=$SHARED_PASSWORD" \
  "ADMIN_PASSWORD=$ADMIN_PASSWORD" \
  "SESSION_SECRET=$SESSION_SECRET" \
  "CORS_ORIGIN=$CORS_ORIGIN" \
  "SECURE_COOKIES=$SECURE_COOKIES" \
  "REPO_TYPE=$REPO_TYPE" \
  -- \
  "$REPO_ROOT/.venv/bin/python" -m uvicorn web.backend.app:app \
    --host 0.0.0.0 --port "$BACKEND_PORT"

# Wait for backend to be ready
echo "  Waiting for backend..."
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${BACKEND_PORT}/api/health" 2>/dev/null)
  if [[ "$code" == "200" || "$code" == "401" ]]; then
    echo "  Backend ready (HTTP $code)."
    break
  fi
  sleep 0.5
done

# ── Frontend ─────────────────────────────────────────────────────────────────
echo "Starting frontend on port ${FRONTEND_PORT}..."
> /tmp/esa-frontend.log
detach "$FRONTEND_PID_FILE" /tmp/esa-frontend.log \
  -- \
  node "$REPO_ROOT/web/frontend/node_modules/.bin/next" dev \
    -H 0.0.0.0 --port "$FRONTEND_PORT"

echo ""
echo "─────────────────────────────────────────────────────────"
echo "  Frontend : http://localhost:${FRONTEND_PORT}"
echo "  Backend  : http://localhost:${BACKEND_PORT}"
echo "  Host pw  : ${SHARED_PASSWORD}"
echo "  Admin pw : ${ADMIN_PASSWORD}"
echo "  Logs     : /tmp/esa-backend.log  /tmp/esa-frontend.log"
echo "  Stop     : kill \$(cat /tmp/esa-backend.pid) \$(cat /tmp/esa-frontend.pid)"
echo "─────────────────────────────────────────────────────────"

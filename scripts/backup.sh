#!/usr/bin/env bash
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
SOURCE_DIR="${SOURCE_DIR:-/app/output}"
B2_BUCKET="${B2_BUCKET:-codescales-esa-backups}"
B2_PREFIX="${B2_PREFIX:-waypoint}"
B2_KEY_ID="${B2_KEY_ID:?B2_KEY_ID is required}"
B2_APP_KEY="${B2_APP_KEY:?B2_APP_KEY is required}"
B2_ENDPOINT="${B2_ENDPOINT:-https://s3.us-west-004.backblazeb2.com}"

RCLONE_REMOTE="b2-backup"
RCLONE_CONFIG_DIR="${RCLONE_CONFIG_DIR:-/config/rclone}"
RCLONE_CONFIG="${RCLONE_CONFIG_DIR}/rclone.conf"

KEEP_HOURLY="${KEEP_HOURLY:-5}"
KEEP_DAILY="${KEEP_DAILY:-5}"

# ── Ensure rclone config exists ─────────────────────────────────────────────
mkdir -p "$RCLONE_CONFIG_DIR"
if [[ ! -f "$RCLONE_CONFIG" ]]; then
  cat > "$RCLONE_CONFIG" <<EOF
[$RCLONE_REMOTE]
type = s3
provider = Other
access_key_id = $B2_KEY_ID
secret_access_key = $B2_APP_KEY
endpoint = $B2_ENDPOINT
acl = private
EOF
fi

# ── Snapshot name ────────────────────────────────────────────────────────────
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_NAME="snapshot-${TIMESTAMP}"

# ── Upload snapshot ────────────────────────────────────────────────────────
echo "[backup] Uploading snapshot: $SNAPSHOT_NAME"
rclone --config "$RCLONE_CONFIG" copy \
  "$SOURCE_DIR" \
  "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/snapshots/${SNAPSHOT_NAME}/" \
  --progress --checksum

# ── Tag as hourly ───────────────────────────────────────────────────────────
echo "[backup] Tagging as hourly"
rclone --config "$RCLONE_CONFIG" copy \
  "$SOURCE_DIR" \
  "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/hourly/${SNAPSHOT_NAME}/" \
  --checksum

# ── Prune hourly (keep newest KEEP_HOURLY) ──────────────────────────────────
echo "[backup] Pruning hourly (keep $KEEP_HOURLY)"
rclone --config "$RCLONE_CONFIG" lsd "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/hourly/" \
  | sort -k2 -k3 \
  | head -n -"$KEEP_HOURLY" \
  | awk '{print $5}' \
  | while IFS= read -r dir; do
      if [[ -n "$dir" ]]; then
        echo "  Removing old hourly: $dir"
        rclone --config "$RCLONE_CONFIG" purge "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/hourly/${dir}/"
      fi
    done

# ── Daily: promote if not already done today ────────────────────────────────
TODAY=$(date -u +%Y%m%d)
DAILY_TAG="${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/daily/${TODAY}/"

if ! rclone --config "$RCLONE_CONFIG" lsd "$DAILY_TAG" &>/dev/null; then
  echo "[backup] Promoting to daily"
  rclone --config "$RCLONE_CONFIG" copy \
    "$SOURCE_DIR" \
    "$DAILY_TAG" \
    --checksum
else
  echo "[backup] Daily snapshot already exists for $TODAY, skipping"
fi

# ── Prune daily (keep newest KEEP_DAILY) ────────────────────────────────────
echo "[backup] Pruning daily (keep $KEEP_DAILY)"
rclone --config "$RCLONE_CONFIG" lsd "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/daily/" \
  | sort -k2 -k3 \
  | head -n -"$KEEP_DAILY" \
  | awk '{print $5}' \
  | while IFS= read -r dir; do
      if [[ -n "$dir" ]]; then
        echo "  Removing old daily: $dir"
        rclone --config "$RCLONE_CONFIG" purge "${RCLONE_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/daily/${dir}/"
      fi
    done

echo "[backup] Done"

#!/usr/bin/env bash
set -euo pipefail

# Write rclone config from env vars
mkdir -p /config/rclone
cat > /config/rclone/rclone.conf <<EOF
[b2-backup]
type = s3
provider = Other
access_key_id = ${B2_KEY_ID}
secret_access_key = ${B2_APP_KEY}
endpoint = ${B2_ENDPOINT:-https://s3.us-west-004.backblazeb2.com}
acl = private
EOF

# Start cron in foreground
echo "[backup] Starting cron with schedule: ${BACKUP_CRON:-0 * * * *}"
crond -f -l 2

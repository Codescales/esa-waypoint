#!/usr/bin/env bash
set -euo pipefail

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

python3 -m venv "$tmpdir/venv"
source "$tmpdir/venv/bin/activate"

pip install -q -e . 2>&1

echo "Checking production imports..."
python3 -c "
from web.backend.app import app
from web.backend.limiter import limiter
print('All production imports OK')
" 2>&1

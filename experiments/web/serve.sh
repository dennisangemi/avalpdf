#!/usr/bin/env bash
# Launch the avalpdf web UI. Dependencies are fetched on the fly by uv, so no
# manual setup is needed (same approach as tool-manual-tagging/serve.sh).
set -euo pipefail
cd "$(dirname "$0")"
exec uv run \
  --with pdfix-sdk \
  --with pikepdf \
  --with rich \
  --with requests \
  python3 app.py "$@"

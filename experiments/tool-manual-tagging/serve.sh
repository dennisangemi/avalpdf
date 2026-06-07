#!/usr/bin/env bash
# Avvia l'editor di tag su una porta libera e apre il browser.
# Uso:  ./serve.sh [file.pdf]
set -euo pipefail
cd "$(dirname "$0")"
exec uv run --with pikepdf --with opendataloader-pdf python3 tagtool.py "$@"

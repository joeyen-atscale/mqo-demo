#!/usr/bin/env bash
# start.sh — launch the mqo-demo Streamlit app (run ./install.sh first).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# Load .env (ANTHROPIC_API_KEY, ATSCALE_OIDC_SECRET, …) if present.
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "ANTHROPIC_API_KEY is not set — edit $ROOT/.env"; exit 1; }
export ATSCALE_OIDC_SECRET="${ATSCALE_OIDC_SECRET:-atscale}"
VENV="$ROOT/mqo-demo/.venv"
exec "${VENV}/bin/streamlit" run "$ROOT/mqo-demo/app.py"

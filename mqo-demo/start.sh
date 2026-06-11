#!/bin/bash
export ATSCALE_OIDC_SECRET="${ATSCALE_OIDC_SECRET:-atscale}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"

DIR="$(cd "$(dirname "$0")" && pwd)"

# Prefer the project venv if present (created via: python3 -m venv .venv && \
# .venv/bin/pip install -r requirements.txt), otherwise fall back to PATH.
if [ -x "$DIR/.venv/bin/streamlit" ]; then
  exec "$DIR/.venv/bin/streamlit" run "$DIR/app.py"
else
  exec streamlit run "$DIR/app.py"
fi

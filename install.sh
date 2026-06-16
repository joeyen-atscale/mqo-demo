#!/usr/bin/env bash
# install.sh — one-shot setup for mqo-demo + the mqo-mcp engine.
#
#   git clone https://github.com/joeyen-atscale/mqo-demo.git
#   cd mqo-demo
#   ./install.sh
#   ./start.sh
#
# Clones/updates the mqo-mcp engine (current main), builds the server + the four
# pipeline helper binaries, sets up the demo's Python venv, and writes a .env you
# fill in with your Anthropic key. Re-running is safe: it pulls the latest engine
# and rebuilds only if something changed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEMO_DIR="$ROOT/mqo-demo"
MQO_MCP_DIR="$ROOT/mqo-mcp"
LOCAL_BIN="$HOME/.local/bin"
MQO_MCP_REPO="https://github.com/joeyen-atscale/mqo-mcp.git"
# The pipeline shells out to these helpers — ALL must be current, not just the
# server (installing the server alone leaves stale bind/route/dax/mdx).
HELPERS=(mqo-mcp-server mqo-bind mqo-route mqo-dax mqo-mdx)

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok(){ echo -e "${G}✓${N} $*"; }; warn(){ echo -e "${Y}!${N} $*"; }; fail(){ echo -e "${R}✗${N} $*"; exit 1; }

echo; echo "=== mqo-demo installer ==="; echo

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
command -v git   >/dev/null || fail "git not found."
command -v cargo >/dev/null || fail "cargo not found. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
command -v python3 >/dev/null || fail "python3 not found. Install Python 3.10+."
python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' \
  || fail "python3 3.10+ required (found $(python3 -V 2>&1 | awk '{print $2}'))."
ok "cargo $(cargo --version | awk '{print $2}') · python $(python3 -V 2>&1 | awk '{print $2}')"
mkdir -p "$LOCAL_BIN"

# ── 2. Clone or update the mqo-mcp engine (current main) ────────────────────────
if [ -d "$MQO_MCP_DIR/.git" ]; then
  echo "Updating mqo-mcp engine to latest main…"
  git -C "$MQO_MCP_DIR" pull --ff-only --quiet && ok "mqo-mcp updated" || warn "could not fast-forward mqo-mcp; using existing checkout"
else
  echo "Cloning mqo-mcp engine…"
  git clone --quiet "$MQO_MCP_REPO" "$MQO_MCP_DIR" && ok "mqo-mcp cloned"
fi
SERVER_VER="$(grep -m1 '^version' "$MQO_MCP_DIR/mqo-mcp-server/Cargo.toml" | sed -E 's/.*"([^"]+)".*/\1/')"
ok "engine version: mqo-mcp-server v$SERVER_VER"

# ── 3. Build + install the server and ALL pipeline helpers ──────────────────────
echo "Building the engine (first build ~2-4 min)…"
cargo build --release --manifest-path "$MQO_MCP_DIR/Cargo.toml" \
  -p mqo-mcp-server -p mqo-catalog-binder -p mqo-backend-router \
  -p mqo-dax-compiler -p mqo-mdx-compiler
REL="$MQO_MCP_DIR/target/release"
for b in "${HELPERS[@]}"; do
  [ -x "$REL/$b" ] || fail "expected built binary missing: $REL/$b"
  install -m755 "$REL/$b" "$LOCAL_BIN/$b"
done
ok "installed ${HELPERS[*]} → $LOCAL_BIN  (the bridge also runs them from $REL)"
case ":$PATH:" in *":$LOCAL_BIN:"*) ;; *) warn "$LOCAL_BIN is not on \$PATH — add: export PATH=\"\$HOME/.local/bin:\$PATH\"";; esac

# ── 4. Demo Python venv ─────────────────────────────────────────────────────────
VENV="$DEMO_DIR/.venv"
[ -d "$VENV" ] || { echo "Creating Python venv…"; python3 -m venv "$VENV"; }
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$DEMO_DIR/requirements.txt"
ok "demo dependencies installed (streamlit, anthropic)"

# ── 5. Config (.env) ────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "wrote $ROOT/.env — edit it and set ANTHROPIC_API_KEY before starting"
else
  ok ".env present"
fi

echo; echo "=== Setup complete (engine v$SERVER_VER) ==="; echo
echo "1. Put your Anthropic key in .env:   ANTHROPIC_API_KEY=sk-ant-..."
echo "2. Launch the demo:                  ./start.sh"
echo "   (opens the Streamlit chat UI in your browser)"
echo

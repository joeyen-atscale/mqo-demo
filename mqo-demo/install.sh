#!/bin/bash
# install.sh — one-shot setup for mqo-demo + mqo-mcp-server
# Run from the mqo-demo directory: bash install.sh
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$DEMO_DIR")"
MCP_DIR="$PARENT_DIR/mqo-mcp-server"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

echo ""
echo "=== mqo-demo installer ==="
echo ""

# ── 1. Prerequisites ────────────────────────────────────────────────────────────

if ! command -v cargo &>/dev/null; then
  fail "cargo not found. Install Rust via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
fi
ok "cargo $(cargo --version | awk '{print $2}')"

if ! command -v python3 &>/dev/null; then
  fail "python3 not found. Install Python 3.10+ from https://python.org"
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  ok "python3 $PY_VER"
else
  fail "python3 $PY_VER found but 3.10+ is required"
fi

# ── 2. mqo-mcp-server ──────────────────────────────────────────────────────────

if [ ! -d "$MCP_DIR" ]; then
  echo ""
  echo "Cloning mqo-mcp-server into $MCP_DIR ..."
  git clone https://github.com/joeyen-atscale/mqo-mcp-server.git "$MCP_DIR"
  ok "cloned mqo-mcp-server"
else
  ok "mqo-mcp-server found at $MCP_DIR"
fi

BINARY="$MCP_DIR/target/release/mqo-mcp-server"
if [ ! -x "$BINARY" ]; then
  echo ""
  echo "Building mqo-mcp-server (this takes ~1 minute the first time)..."
  cargo build --release --manifest-path "$MCP_DIR/Cargo.toml"
  ok "built $BINARY"
else
  ok "binary already built: $BINARY"
fi

# ── 3. Python venv ─────────────────────────────────────────────────────────────

VENV="$DEMO_DIR/.venv"
if [ ! -d "$VENV" ]; then
  echo ""
  echo "Creating Python venv..."
  python3 -m venv "$VENV"
  ok "venv created"
fi

echo "Installing Python dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$DEMO_DIR/requirements.txt"
ok "dependencies installed"

# ── 4. Environment variables ───────────────────────────────────────────────────

echo ""
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  warn "ANTHROPIC_API_KEY is not set. Add it to your shell profile:"
  echo "    export ANTHROPIC_API_KEY=\"sk-ant-...\""
else
  ok "ANTHROPIC_API_KEY is set"
fi

if [ -z "${ATSCALE_OIDC_SECRET:-}" ]; then
  warn "ATSCALE_OIDC_SECRET not set — will default to 'atscale' at runtime"
else
  ok "ATSCALE_OIDC_SECRET is set"
fi

# ── 5. Done ────────────────────────────────────────────────────────────────────

echo ""
echo "=== Setup complete ==="
echo ""
echo "Start the demo:"
echo "    export ANTHROPIC_API_KEY=\"sk-ant-...\""
echo "    cd $DEMO_DIR && ./start.sh"
echo ""

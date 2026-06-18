#!/bin/bash
# install.sh — one-shot setup for mqo-demo + the full MQO fleet
# Run from the mqo-demo directory: bash install.sh
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$DEMO_DIR")"
MQO_MCP_DIR="$PARENT_DIR/mqo-mcp"
LOCAL_BIN="$HOME/.local/bin"

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

mkdir -p "$LOCAL_BIN"

# ── 2. Clone + build the MQO fleet monorepo ────────────────────────────────────

if [ ! -d "$MQO_MCP_DIR" ]; then
  echo ""
  echo "Cloning mqo-mcp monorepo..."
  git clone https://github.com/joeyen-atscale/mqo-mcp.git "$MQO_MCP_DIR"
  ok "cloned mqo-mcp"
else
  ok "mqo-mcp found at $MQO_MCP_DIR"
fi

FLEET_BINARIES=(mqo-mcp-server mqo-bind mqo-route mqo-dax mqo-mdx)
NEEDS_BUILD=false
for bin in "${FLEET_BINARIES[@]}"; do
  if [ ! -x "$LOCAL_BIN/$bin" ]; then
    NEEDS_BUILD=true
    break
  fi
done

if [ "$NEEDS_BUILD" = true ]; then
  echo ""
  echo "Building fleet (~2 min first time)..."
  cargo build --release --manifest-path "$MQO_MCP_DIR/Cargo.toml" \
    -p mqo-mcp-server -p mqo-catalog-binder -p mqo-backend-router \
    -p mqo-dax-compiler -p mqo-mdx-compiler --quiet

  RELEASE="$MQO_MCP_DIR/target/release"
  cp "$RELEASE/mqo-mcp-server" "$LOCAL_BIN/mqo-mcp-server"
  cp "$RELEASE/mqo-bind"       "$LOCAL_BIN/mqo-bind"
  cp "$RELEASE/mqo-route"      "$LOCAL_BIN/mqo-route"
  cp "$RELEASE/mqo-dax"        "$LOCAL_BIN/mqo-dax"
  cp "$RELEASE/mqo-mdx"        "$LOCAL_BIN/mqo-mdx"
  ok "fleet binaries installed to $LOCAL_BIN"
else
  ok "fleet binaries already installed"
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
echo "    # 1. Edit .env in the repo root and fill in ANTHROPIC_API_KEY, ATSCALE_PG_USER, ATSCALE_PG_PASSWORD"
echo "    #    (copy from .env.example if you haven't already)"
echo "    # 2. Run the root launcher (it loads .env automatically):"
echo "    cd $PARENT_DIR && ./start.sh"
echo ""

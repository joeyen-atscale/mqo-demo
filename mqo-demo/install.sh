#!/bin/bash
# install.sh — one-shot setup for mqo-demo + the full MQO fleet
# Run from the mqo-demo directory: bash install.sh
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$DEMO_DIR")"
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

# ── 2. Clone + build the MQO fleet ─────────────────────────────────────────────
# mqo-mcp-server orchestrates these four binaries as subprocesses.
# They're installed to ~/.local/bin, which the server checks automatically.

clone_and_build() {
  local repo="$1"
  local binary="$2"   # binary name to install (empty = lib only, skip install)
  local dir="$PARENT_DIR/$repo"

  if [ ! -d "$dir" ]; then
    echo "  Cloning $repo..."
    git clone "https://github.com/joeyen-atscale/$repo.git" "$dir" --quiet
  fi

  if [ -n "$binary" ]; then
    if [ -x "$LOCAL_BIN/$binary" ]; then
      ok "$binary already installed"
      return
    fi
    echo "  Building $repo..."
    cargo build --release --manifest-path "$dir/Cargo.toml" --quiet
    cp "$dir/target/release/$binary" "$LOCAL_BIN/$binary"
    ok "installed $binary → $LOCAL_BIN/$binary"
  fi
}

echo "Setting up MQO fleet..."
clone_and_build "mqo-spec"             ""
clone_and_build "mqo-catalog-binder"   "mqo-bind"
clone_and_build "mqo-backend-router"   "mqo-route"
clone_and_build "mqo-dax-compiler"     "mqo-dax"
clone_and_build "mqo-mdx-compiler"     "mqo-mdx"
clone_and_build "mqo-mcp-server"       "mqo-mcp-server"

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

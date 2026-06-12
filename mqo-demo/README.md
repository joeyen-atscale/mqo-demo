# mqo-demo

Ask a plain-English BI question. Get a governed Vega-Lite chart in under 15 seconds.

`mqo-demo` is a Streamlit chat UI that drives `claude-sonnet-4-6` over the AtScale semantic layer via `mqo-mcp-server`. You type a question; Claude builds a Multidimensional Query Object, runs it against AtScale, and renders a chart — no SQL, no hardcoded queries. Refinement is conversational: *"break that down by quarter"*, *"add a region filter"*, *"show net profit instead"*.

---

## Quick start

```bash
git clone https://github.com/joeyen-atscale/mqo-demo.git
cd mqo-demo
bash install.sh
```

`install.sh` clones and builds `mqo-mcp-server`, creates a Python venv, installs deps, and checks your env vars. One command, done.

> **⚠️ Use `install.sh` — don't run `cargo build` at the repo root.** The root
> `Cargo.toml` is a dev convenience whose workspace members live in the
> **gitignored** sibling `mqo-mcp/` clone, so a bare `cargo build` on a fresh
> checkout fails with "missing members." `install.sh` builds the fleet against
> the cloned monorepo's own manifest (`mqo-mcp/Cargo.toml`); if you must build
> by hand, target that manifest:
> `cargo build --release --manifest-path ../mqo-mcp/Cargo.toml -p mqo-mcp-server -p mqo-catalog-binder -p mqo-backend-router -p mqo-dax-compiler -p mqo-mdx-compiler`.

Then:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
./start.sh
```

Open `http://localhost:8501` and try *"Show total store sales by year"*.

---

## Prerequisites

- **Rust 1.88+** — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Python 3.10+**
- **ANTHROPIC_API_KEY** — from [console.anthropic.com](https://console.anthropic.com)
- **ATSCALE_OIDC_SECRET** — defaults to `atscale` if unset

---

## How it works

```
You type a question
      │
      ▼
Claude (claude-sonnet-4-6)
  builds an MQO, calls tools
      │  tool-use loop (max 12 iterations)
      ▼
mcp_bridge.py  ──stdio JSON-RPC──►  mqo-mcp-server (Rust)
                                           │
                                           ▼
                                  AtScale XMLA / DAX
                                  tpcds_benchmark_model
                                           │
                                           ▼
                                  Vega-Lite chart in chat
```

The left sidebar shows the server connection status, active model path, last query backend (`dax` / `mdx` / `sql`), and the raw MQO sent on the most recent query — useful for seeing exactly what AtScale received.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI + Claude tool-use loop |
| `mcp_bridge.py` | stdio JSON-RPC bridge; normalizes XMLA column keys |
| `install.sh` | One-shot setup: clones + builds server, creates venv |
| `start.sh` | Venv-preferring launcher |
| `requirements.txt` | `anthropic>=0.28.0`, `streamlit>=1.35.0` |

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `ATSCALE_OIDC_SECRET` | No | `atscale` | OIDC client secret for AtScale |
| `MQO_MCP_BINARY` | No | auto-resolved | Override path to `mqo-mcp-server` binary |
| `MQO_MCP_CATALOG` | No | auto-resolved | Override path to `tpcds_catalog.json` |

The binary is resolved automatically: sibling-repo build first (`../mqo-mcp-server/target/release/`), then shared workspace build (`../target/release/`), then `MQO_MCP_BINARY`.

---

## Notes

- Demo / POC only — no auth, no multi-user isolation.
- Server stderr is logged to `/tmp/mqo-mcp-server.stderr.log` for debugging.
- Model path must be the short form `tpcds_benchmark_model` — the fully-qualified path fails with `xmla_coords_not_found`.

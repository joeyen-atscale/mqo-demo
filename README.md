# mqo-demo

**Ask a plain-English business question, get a governed chart — the model never writes SQL.**

`mqo-demo` is a Streamlit chat app that drives Claude over the AtScale semantic layer through
[`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp). You type a question; Claude builds a
typed, catalog-validated **Multidimensional Query Object (MQO)**, the server grounds and runs it
against AtScale, and the answer comes back as a rendered Vega-Lite chart — with every field bound
to a certified metric definition, so there are no hallucinated columns or silently-wrong numbers.

```
Plain English → Claude builds an MQO → validate & bind to the live catalog
   → run on the AtScale cluster → profile → rendered chart
```

## Repository layout

```
.
├── install.sh         ← one-shot setup (run this)
├── start.sh           ← launcher
├── .env.example       ← copy to .env, set your Anthropic key
├── mqo-demo/          ← the Streamlit app
│   ├── app.py             chat UI + Claude tool loop
│   └── mcp_bridge.py      stdio JSON-RPC bridge to mqo-mcp-server
├── ARCHITECTURE.md    ← how the pieces fit together
└── (Rust workspace crates used by the demo)
```

## Quick start — three commands

```bash
git clone https://github.com/joeyen-atscale/mqo-demo.git
cd mqo-demo
./install.sh                         # clone+build the engine, build binaries, make a venv, write .env
#  → edit .env and set ANTHROPIC_API_KEY=sk-ant-...
./start.sh                           # opens the chat UI at http://localhost:8501
```

`./install.sh` clones the [`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp) engine at the
**current `main`** (re-running pulls latest and rebuilds only if needed), builds the server **and
all four pipeline helpers** (`mqo-bind`/`route`/`dax`/`mdx` — the engine shells out to them, so they
must be current together), installs the Python deps, and writes `.env` from `.env.example`.
`./start.sh` loads `.env` and launches the app. Both repos are public.

## Prerequisites

- **Rust / cargo** and **Python 3.10+** (the installer checks both and fails fast with guidance).
- An **`ANTHROPIC_API_KEY`**.
- **Network access to the AtScale cluster** the demo targets (`mcp-aws.atscaleinternal.com`).
  The code is public, but the app only *runs* where that cluster is reachable — i.e. on AtScale's
  network. `ATSCALE_OIDC_SECRET` defaults to `atscale` if unset.

## How it works

The demo is the consumer-facing surface over the `mqo-mcp` engine: catalog discovery, a grounded
`query_multidimensional` call (never raw SQL), server-side dataset **handles** so result rows never
flood the model's context, and a chart toolkit. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the
end-to-end pipeline and [`mqo-demo/README.md`](./mqo-demo/README.md) for app-level detail.

## Status & license

Public demo / POC — no auth or multi-user isolation. Built on the AtScale MQO/MCP fleet.
Dual-licensed **MIT OR Apache-2.0**.

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
├── mqo-demo/          ← the Streamlit app + installer (start here)
│   ├── app.py             chat UI + Claude tool loop
│   ├── mcp_bridge.py      stdio JSON-RPC bridge to mqo-mcp-server
│   ├── install.sh         one-shot setup (clones + builds the engine, makes a venv)
│   └── start.sh           launcher
├── ARCHITECTURE.md    ← how the pieces fit together
└── (Rust workspace crates used by the demo)
```

## Quick start

```bash
git clone https://github.com/joeyen-atscale/mqo-demo.git
cd mqo-demo/mqo-demo          # the app lives in the mqo-demo/ subdirectory
bash install.sh              # clones + builds joeyen-atscale/mqo-mcp, builds 5 binaries, makes a venv
export ANTHROPIC_API_KEY="sk-ant-..."
./start.sh                   # opens http://localhost:8501
```

`install.sh` clones and builds the [`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp) engine
(both repos are public), installs the Python deps, and checks your environment.

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

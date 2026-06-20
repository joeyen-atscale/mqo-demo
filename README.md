# mqo-demo

**Ask a plain-English business question, get a governed chart — Claude never writes SQL.**

`mqo-demo` is a Streamlit chat app that drives Claude over the AtScale semantic layer through
[`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp). You type a question; Claude builds a typed,
catalog-validated **Multidimensional Query Object (MQO)**; the server binds it to the live catalog,
runs it against AtScale, and the answer comes back as a rendered Vega-Lite chart. Every field is
bound to a certified metric definition, so there are no hallucinated columns and no silently-wrong
numbers.

```
Plain English → Claude builds an MQO → bind & validate against the live catalog
   → run on the AtScale cluster → profile the result → rendered chart
```

## Why it exists

Text-to-SQL over a multidimensional model is a sucker's game. The model knows what a measure is,
which hierarchy levels are compatible, how a date role joins — an LLM writing free SQL knows none
of that, so it guesses, and a wrong guess is a query that costs warehouse credits before it fails.
MQO closes the grammar: instead of an open SQL string, Claude fills in a small, enumerable object
whose every field is checked against the catalog before anything reaches the engine. The set of
queries Claude *can* express is the set of queries the model actually supports. That is the whole
trick — constrain the output space and the hallucinations have nowhere to go.

## Quick start

```bash
git clone https://github.com/joeyen-atscale/mqo-demo.git
cd mqo-demo
./install.sh        # clones+builds the mqo-mcp engine, builds the binaries, makes a venv, writes .env
# → edit .env: set ANTHROPIC_API_KEY, and your AtScale PGWire username/password
./start.sh          # opens the chat UI at http://localhost:8501
```

Then ask *"Show total store sales by year"* and refine it conversationally — *"break that down by
quarter"*, *"top 10 only"*, *"show net profit instead"*.

`install.sh` clones [`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp) at the current `main`,
builds the server plus the four pipeline helper binaries the engine shells out to (bind / route /
dax / mdx — they have to move together), installs the Python deps into a venv, and writes `.env`
from `.env.example`. Re-running is safe: it pulls latest and rebuilds only what changed.

> Run `./install.sh`, not a bare `cargo build` at the repo root. The root `Cargo.toml` is a dev
> convenience; its workspace members live in the **gitignored** `mqo-mcp/` clone, so `cargo build`
> on a fresh checkout fails with "missing members."

## Prerequisites

- **Rust / cargo** and **Python 3.10+** — the installer checks both and fails fast with guidance.
- An **`ANTHROPIC_API_KEY`** (from console.anthropic.com).
- **AtScale PGWire credentials** (`ATSCALE_PG_USER` / `ATSCALE_PG_PASSWORD`) for the SQL path.
- **Network access to the AtScale cluster** the demo targets (default `mcp-aws.atscaleinternal.com`).
  The code is public; the app only *runs* where that cluster is reachable — i.e. on AtScale's
  network.

Configuration is by environment variable, set in `.env` (loaded by `start.sh`). See
[`.env.example`](./.env.example) for the full list; `ATSCALE_ENDPOINT` / `ATSCALE_XMLA_URL` /
`ATSCALE_MODEL` redirect the demo at a different cluster or model.

## How it works

Claude is given the 16 tools the `mqo-mcp` server exposes and a system prompt that teaches it the
MQO shape and the handle protocol. One turn is a tool-use loop (up to 12 iterations):

```
You type a question
  → Claude builds an MQO and calls query_multidimensional
  → mcp_bridge.py speaks stdio JSON-RPC to mqo-mcp-server (Rust)
  → server binds the MQO, routes it (dax / mdx / sql), runs it on AtScale
  → result is stored server-side; Claude gets back a summary + a handle, not the raw rows
  → dataset_chart(handle, ...) → a Vega-Lite v5 spec the UI renders inline
```

Two ideas carry the design:

- **The MQO is closed, not open.** `query_multidimensional` takes an object, not a SQL string. The
  param-validator rejects any measure or dimension level that isn't in the catalog *before* the
  query runs, with a nearest-match suggestion for Claude to retry against.
- **Results are handles, not rows.** A query's rows stay on the server. Claude gets a typed column
  summary and an opaque handle, then refines by operating on the handle (`dataset_top_n`,
  `dataset_filter`, `dataset_aggregate`, …) — never by re-querying AtScale and never by doing the
  arithmetic itself. The numbers stay governed, and a 10,000-row result costs the same in context
  as a 50-row one.

The left sidebar shows connection status, the active model and LLM, the backend the last query used
(`dax` / `mdx` / `sql`), and the raw MQO sent on the most recent query — so you can see exactly
what AtScale received.

## Layout

```
.
├── install.sh        one-shot setup (run this)
├── start.sh          launcher (loads .env, runs the Streamlit app)
├── .env.example      copy to .env, fill in keys and credentials
├── mqo-demo/         the Streamlit app
│   ├── app.py            chat UI + Claude tool-use loop + system prompt
│   ├── mcp_bridge.py     stdio JSON-RPC bridge; normalizes XMLA column keys
│   └── tpcds_nlq.json    bundled TPC-DS questions for the starter chips
├── ARCHITECTURE.md   how the engine pieces fit together
└── (Rust workspace crates the engine is built from)
```

[`ARCHITECTURE.md`](./ARCHITECTURE.md) covers the end-to-end pipeline and crate boundaries;
[`mqo-demo/README.md`](./mqo-demo/README.md) covers app-level detail and the full env-var table.

## Where it fits

This is the consumer-facing surface over the [`mqo-mcp`](https://github.com/joeyen-atscale/mqo-mcp)
engine — the typed MQO pipeline, catalog binder, backend router, compilers, handle store, and MCP
server. `mqo-demo` is what a stakeholder sees; `mqo-mcp` is what does the work.

## Status & license

Demo / POC. No auth, no multi-user isolation — single-process, run it on your own machine against a
reachable cluster. Server stderr is logged to `/tmp/mqo-mcp-server.stderr.log` for debugging.
Dual-licensed **MIT OR Apache-2.0**.
